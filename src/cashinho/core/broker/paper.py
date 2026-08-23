"""PaperBroker: executa ordens contra candles, sem dinheiro real.

O que ele simula de verdade:

- **spread e slippage** - o preco executado nunca e' o do grafico;
- **taxas** - corretagem e taxas da B3 nas duas pontas;
- **saldo** - compra que nao cabe no caixa e' rejeitada;
- **posicao existente** - ordem que reduz posicao e' tratada como
  encerramento, e nao como abertura de posicao contraria;
- **OCO** - quando uma perna executa, a outra e' cancelada.

Uma diferenca deliberada em relacao ao Backtest Engine: aqui a ordem a
mercado executa **na hora**, no ultimo preco conhecido (com spread e
slippage), porque e' isso que acontece quando alguem clica em comprar. No
backtest, ela espera a abertura do candle seguinte, porque la a decisao foi
tomada com o candle ja fechado.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Optional, Sequence

from ...models import BRT, Candle, Direction, formata_dinheiro
from ..backtest.costs import ModeloCustos
from .base import Broker, BrokerError, OrdemBloqueadaError, OrdemInvalidaError
from .modelos import (
    Balance,
    Operacao,
    Order,
    OrderStatus,
    OrderType,
    Position,
    novo_id,
)


@dataclass(frozen=True)
class ConfigPaper:
    """Ajustes da simulacao."""

    capital_inicial: float = 100_000.0
    custos: ModeloCustos = field(default_factory=ModeloCustos)
    prioridade_intracandle: str = "stop"  # quando stop e alvo cabem no mesmo candle
    permitir_venda_descoberto: bool = True
    kill_switch_cancela_pendentes: bool = True

    def __post_init__(self) -> None:
        if self.capital_inicial <= 0:
            raise ValueError("capital_inicial precisa ser maior que zero")
        if self.prioridade_intracandle not in ("stop", "alvo"):
            raise ValueError("prioridade_intracandle deve ser 'stop' ou 'alvo'")


class PaperBroker(Broker):
    """Corretora simulada."""

    nome = "paper"
    simulado = True

    def __init__(self, config: Optional[ConfigPaper] = None,
                 relogio=None):
        self.config = config or ConfigPaper()
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self.saldo = self.config.capital_inicial
        self._ordens: dict[str, Order] = {}
        self._posicoes: dict[str, Position] = {}
        self._operacoes: list[Operacao] = []
        self._precos: dict[str, float] = {}
        self._custos_totais = 0.0
        self._pnl_por_dia: dict[date, float] = {}
        self.kill_switch_ativo = False
        self.kill_switch_motivo = ""
        self._dia: Optional[date] = None

    # ------------------------------------------------------------------
    # interface Broker
    # ------------------------------------------------------------------
    def place_order(self, order: Order) -> Order:
        """Envia a ordem. Ordem a mercado executa na hora; as demais ficam pendentes."""
        agora = self._relogio()
        order.criada_em = order.criada_em or agora
        order.atualizada_em = agora

        problema = self._validar(order)
        if problema:
            return self._rejeitar(order, problema)

        self._ordens[order.id] = order
        if order.tipo is OrderType.MARKET:
            preco = self._precos.get(order.symbol.upper())
            if preco is None:
                return self._rejeitar(order, "sem preco conhecido para executar a mercado")
            self._executar(order, preco, agora, ordem_limitada=False)
        return order

    def place_oco(self, stop_loss: Order, take_profit: Order) -> tuple[Order, Order]:
        """Envia um par ligado: quando um executa, o outro e' cancelado."""
        grupo = novo_id("oco")
        stop_loss.oco_id = grupo
        take_profit.oco_id = grupo
        return self.place_order(stop_loss), self.place_order(take_profit)

    def cancel_order(self, order_id: str) -> Order:
        order = self._ordens.get(order_id)
        if order is None:
            raise BrokerError(f"ordem desconhecida: {order_id}")
        if not order.viva:
            return order
        order.status = OrderStatus.CANCELADA
        order.motivo = order.motivo or "cancelada pelo operador"
        order.atualizada_em = self._relogio()
        return order

    def get_orders(self, symbol: Optional[str] = None, abertas: bool = False) -> list[Order]:
        ordens = list(self._ordens.values())
        if symbol:
            alvo = symbol.upper()
            ordens = [o for o in ordens if o.symbol.upper() == alvo]
        if abertas:
            ordens = [o for o in ordens if o.viva]
        return sorted(ordens, key=lambda o: (o.criada_em or datetime.min.replace(tzinfo=BRT), o.id))

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        if symbol:
            p = self._posicoes.get(symbol.upper())
            return [p] if p else []
        return sorted(self._posicoes.values(), key=lambda p: p.symbol)

    def get_balance(self) -> Balance:
        exposicao = sum(abs(p.quantidade) * self._preco(p.symbol, p.preco_medio)
                        for p in self._posicoes.values())
        valor_posicoes = sum(p.valor(self._preco(p.symbol, p.preco_medio))
                             for p in self._posicoes.values())
        return Balance(
            saldo=round(self.saldo, 2),
            patrimonio=round(self.saldo + valor_posicoes, 2),
            exposicao=round(exposicao, 2),
            pnl_dia=round(self.pnl_dia(), 2),
            pnl_acumulado=round(self.pnl_acumulado(), 2),
            capital_inicial=self.config.capital_inicial,
            posicoes_abertas=len(self._posicoes),
            ordens_abertas=len(self.get_orders(abertas=True)),
            custos_totais=round(self._custos_totais, 2),
        )

    def get_trades(self) -> list[Operacao]:
        return list(self._operacoes)

    # ------------------------------------------------------------------
    # kill switch
    # ------------------------------------------------------------------
    def acionar_kill_switch(self, motivo: str = "acionado manualmente") -> list[Order]:
        """Bloqueia novas operacoes na hora.

        Ordens pendentes sao canceladas (senao "imediatamente" seria mentira:
        elas continuariam executando). Posicoes abertas **permanecem** - e
        ordens que as reduzem continuam permitidas, porque uma trava que
        impede voce de sair de uma posicao seria pior do que trava nenhuma.
        """
        self.kill_switch_ativo = True
        self.kill_switch_motivo = motivo
        if not self.config.kill_switch_cancela_pendentes:
            return []
        canceladas = []
        for o in self.get_orders(abertas=True):
            if o.tipo.fecha_posicao:
                continue  # protecao de posicao aberta continua valendo
            o.status = OrderStatus.CANCELADA
            o.motivo = f"kill switch: {motivo}"
            o.atualizada_em = self._relogio()
            canceladas.append(o)
        return canceladas

    def liberar_kill_switch(self) -> None:
        self.kill_switch_ativo = False
        self.kill_switch_motivo = ""

    # ------------------------------------------------------------------
    # avanco do mercado
    # ------------------------------------------------------------------
    def atualizar_preco(self, symbol: str, preco: float) -> None:
        self._precos[symbol.upper()] = preco

    def processar(self, symbol: str, candle: Candle) -> list[Order]:
        """Avanca um candle: dispara o que tiver de disparar."""
        alvo = symbol.upper()
        self._virar_dia(candle.ts.date())
        executadas: list[Order] = []

        pendentes = [o for o in self.get_orders(alvo, abertas=True)]
        # a ordem de checagem importa quando stop e alvo cabem no mesmo candle
        if self.config.prioridade_intracandle == "stop":
            pendentes.sort(key=lambda o: 0 if o.tipo in (OrderType.STOP, OrderType.STOP_LOSS) else 1)
        else:
            pendentes.sort(key=lambda o: 0 if o.tipo is OrderType.TAKE_PROFIT else 1)

        for order in pendentes:
            if not order.viva:
                continue  # pode ter sido cancelada por um OCO neste mesmo candle
            gatilho = self._gatilho(order, candle)
            if gatilho is None:
                continue
            preco, limitada = gatilho
            self._executar(order, preco, candle.ts, ordem_limitada=limitada)
            if order.status is OrderStatus.EXECUTADA:
                executadas.append(order)
                self._cancelar_par_oco(order)

        self._precos[alvo] = candle.close
        return executadas

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------
    def _validar(self, order: Order) -> str:
        if order.quantidade <= 0:
            return f"quantidade invalida ({order.quantidade})"
        if not order.symbol or not order.symbol.strip():
            return "ativo nao informado"
        if order.tipo.precisa_limite and order.preco_limite is None:
            return f"ordem {order.tipo.value} exige preco limite"
        if order.tipo.precisa_disparo and order.preco_disparo is None:
            return f"ordem {order.tipo.value} exige preco de disparo"
        for campo in ("preco_limite", "preco_disparo"):
            valor = getattr(order, campo)
            if valor is not None and valor <= 0:
                return f"{campo} invalido ({valor})"

        posicao = self._posicoes.get(order.symbol.upper())
        reduz = self._reduz_posicao(order, posicao)

        if self.kill_switch_ativo and not reduz:
            return f"kill switch acionado: {self.kill_switch_motivo}"
        if order.tipo.fecha_posicao and posicao is None:
            return f"ordem {order.tipo.value} sem posicao aberta em {order.symbol.upper()}"
        if not order.compra and posicao is None and not self.config.permitir_venda_descoberto:
            return "venda a descoberto desligada na configuracao"
        if order.compra and not reduz:
            preco = order.preco_limite or order.preco_disparo or self._precos.get(order.symbol.upper())
            if preco is not None:
                necessario = order.quantidade * preco + self.config.custos.taxas(order.quantidade, preco)
                if necessario > self.saldo:
                    return (f"saldo insuficiente: precisa de {formata_dinheiro(necessario)}, "
                            f"tem {formata_dinheiro(self.saldo)}")
        return ""

    def _reduz_posicao(self, order: Order, posicao: Optional[Position]) -> bool:
        if posicao is None:
            return False
        return (posicao.quantidade > 0 and not order.compra) or (
            posicao.quantidade < 0 and order.compra
        )

    def _rejeitar(self, order: Order, motivo: str) -> Order:
        order.status = OrderStatus.REJEITADA
        order.motivo = motivo
        order.atualizada_em = self._relogio()
        self._ordens[order.id] = order
        return order

    def _gatilho(self, order: Order, candle: Candle) -> Optional[tuple[float, bool]]:
        """(preco de execucao, e' ordem limitada?) ou None se nao disparou."""
        if order.tipo is OrderType.MARKET:
            return candle.open, False

        if order.tipo in (OrderType.LIMIT, OrderType.TAKE_PROFIT):
            limite = order.preco_limite
            if order.compra and candle.low <= limite:
                return (min(candle.open, limite), True)
            if not order.compra and candle.high >= limite:
                return (max(candle.open, limite), True)
            return None

        disparo = order.preco_disparo
        # stop de compra dispara para cima; de venda, para baixo
        if order.compra:
            if candle.high >= disparo:
                return (max(candle.open, disparo), False)
        else:
            if candle.low <= disparo:
                return (min(candle.open, disparo), False)
        return None

    def _executar(self, order: Order, preco_base: float, quando: datetime,
                  ordem_limitada: bool) -> None:
        posicao = self._posicoes.get(order.symbol.upper())
        reduz = self._reduz_posicao(order, posicao)
        direcao_da_posicao = order.side if not reduz else (
            Direction.LONG if posicao.quantidade > 0 else Direction.SHORT
        )
        preco = self.config.custos.preco_execucao(
            preco_base, direcao_da_posicao, entrando=not reduz, ordem_limitada=ordem_limitada
        )
        custos = self.config.custos.taxas(order.quantidade, preco)

        if order.compra and not reduz:
            necessario = order.quantidade * preco + custos
            if necessario > self.saldo:
                self._rejeitar(order, f"saldo insuficiente na execucao "
                                      f"({formata_dinheiro(necessario)})")
                return

        order.status = OrderStatus.EXECUTADA
        order.preco_executado = preco
        order.executada_em = quando
        order.custos = custos
        order.atualizada_em = quando
        self._custos_totais += custos
        self._virar_dia(quando.date())
        self._aplicar(order, preco, custos, quando)

    def _aplicar(self, order: Order, preco: float, custos: float, quando: datetime) -> None:
        chave = order.symbol.upper()
        posicao = self._posicoes.get(chave)
        sinal = 1 if order.compra else -1
        quantidade = order.quantidade * sinal

        # caixa: compra paga, venda recebe; custos sempre saem
        self.saldo -= order.quantidade * preco * sinal
        self.saldo -= custos

        if posicao is None:
            self._posicoes[chave] = Position(chave, quantidade, preco, quando)
            return

        if (posicao.quantidade > 0) == (quantidade > 0):
            # aumenta a posicao: preco medio ponderado
            total = posicao.quantidade + quantidade
            posicao.preco_medio = (
                posicao.preco_medio * posicao.quantidade + preco * quantidade
            ) / total
            posicao.quantidade = total
            return

        # reduz ou inverte
        fechada = min(abs(quantidade), abs(posicao.quantidade))
        self._registrar_operacao(posicao, fechada, preco, custos, quando, order)
        restante = posicao.quantidade + quantidade
        if restante == 0:
            del self._posicoes[chave]
        elif (restante > 0) == (posicao.quantidade > 0):
            posicao.quantidade = restante
        else:
            self._posicoes[chave] = Position(chave, restante, preco, quando)

    def _registrar_operacao(self, posicao: Position, quantidade: int, preco: float,
                            custos: float, quando: datetime, order: Order) -> None:
        operacao = Operacao(
            symbol=posicao.symbol,
            direcao=posicao.direcao,
            quantidade=quantidade,
            preco_entrada=posicao.preco_medio,
            preco_saida=preco,
            aberta_em=posicao.aberta_em,
            fechada_em=quando,
            custos=custos,
            motivo=order.tipo.value,
        )
        self._operacoes.append(operacao)
        dia = quando.date()
        self._pnl_por_dia[dia] = self._pnl_por_dia.get(dia, 0.0) + operacao.resultado

    def _cancelar_par_oco(self, executada: Order) -> None:
        if not executada.oco_id:
            return
        for o in self._ordens.values():
            if o.oco_id == executada.oco_id and o.id != executada.id and o.viva:
                o.status = OrderStatus.CANCELADA
                o.motivo = f"par OCO {executada.id} executou"
                o.atualizada_em = executada.executada_em

    def _preco(self, symbol: str, padrao: float) -> float:
        return self._precos.get(symbol.upper(), padrao)

    def _virar_dia(self, dia: date) -> None:
        if self._dia is None:
            self._dia = dia
        elif dia != self._dia:
            self._dia = dia
        self._pnl_por_dia.setdefault(dia, 0.0)

    # ------------------------------------------------------------------
    def pnl_dia(self, dia: Optional[date] = None) -> float:
        """Resultado realizado do pregao."""
        alvo = dia or self._dia
        return self._pnl_por_dia.get(alvo, 0.0) if alvo else 0.0

    def pnl_acumulado(self) -> float:
        return sum(o.resultado for o in self._operacoes)

    def pnl_aberto(self) -> float:
        return sum(p.pnl_aberto(self._preco(p.symbol, p.preco_medio))
                   for p in self._posicoes.values())

    # ------------------------------------------------------------------
    # persistencia (a pagina precisa sobreviver entre chamadas)
    # ------------------------------------------------------------------
    def para_dict(self) -> dict:
        return {
            "capital_inicial": self.config.capital_inicial,
            "saldo": round(self.saldo, 6),
            "custos_totais": round(self._custos_totais, 6),
            "dia": self._dia.isoformat() if self._dia else None,
            "kill_switch_ativo": self.kill_switch_ativo,
            "kill_switch_motivo": self.kill_switch_motivo,
            "precos": dict(self._precos),
            "pnl_por_dia": {d.isoformat(): round(v, 6) for d, v in self._pnl_por_dia.items()},
            "ordens": [
                {
                    **o.para_dict(),
                    "criada_em": o.criada_em.isoformat() if o.criada_em else None,
                    "atualizada_em": o.atualizada_em.isoformat() if o.atualizada_em else None,
                    "referencia": o.referencia,
                }
                for o in self._ordens.values()
            ],
            "posicoes": [
                {**p.para_dict(), "stop": p.stop, "alvo": p.alvo}
                for p in self._posicoes.values()
            ],
            "operacoes": [o.para_dict() for o in self._operacoes],
        }

    @classmethod
    def de_dict(cls, dados: dict, config: Optional[ConfigPaper] = None,
                relogio=None) -> "PaperBroker":
        from datetime import date as _date
        from datetime import datetime as _dt

        cfg = config or ConfigPaper(capital_inicial=float(dados.get("capital_inicial", 100_000.0)))
        broker = cls(cfg, relogio)
        broker.saldo = float(dados.get("saldo", cfg.capital_inicial))
        broker._custos_totais = float(dados.get("custos_totais", 0.0))
        broker._dia = _date.fromisoformat(dados["dia"]) if dados.get("dia") else None
        broker.kill_switch_ativo = bool(dados.get("kill_switch_ativo", False))
        broker.kill_switch_motivo = dados.get("kill_switch_motivo", "")
        broker._precos = {k.upper(): float(v) for k, v in (dados.get("precos") or {}).items()}
        broker._pnl_por_dia = {
            _date.fromisoformat(k): float(v) for k, v in (dados.get("pnl_por_dia") or {}).items()
        }

        for d in dados.get("ordens", []):
            ordem = Order(
                symbol=d["symbol"], side=Direction(d["side"]), tipo=OrderType(d["tipo"]),
                quantidade=int(d["quantidade"]), preco_limite=d.get("preco_limite"),
                preco_disparo=d.get("preco_disparo"), id=d["id"],
                status=OrderStatus(d["status"]),
                criada_em=_dt.fromisoformat(d["criada_em"]) if d.get("criada_em") else None,
                atualizada_em=_dt.fromisoformat(d["atualizada_em"]) if d.get("atualizada_em") else None,
                preco_executado=d.get("preco_executado"),
                executada_em=_dt.fromisoformat(d["executada_em"]) if d.get("executada_em") else None,
                custos=float(d.get("custos", 0.0)), oco_id=d.get("oco_id"),
                referencia=d.get("referencia", ""), motivo=d.get("motivo", ""),
                stop_referencia=d.get("stop_referencia"),
            )
            broker._ordens[ordem.id] = ordem

        for d in dados.get("posicoes", []):
            broker._posicoes[d["symbol"].upper()] = Position(
                symbol=d["symbol"], quantidade=int(d["quantidade"]),
                preco_medio=float(d["preco_medio"]),
                aberta_em=_dt.fromisoformat(d["aberta_em"]),
                stop=d.get("stop"), alvo=d.get("alvo"),
            )

        for d in dados.get("operacoes", []):
            broker._operacoes.append(Operacao(
                symbol=d["symbol"], direcao=Direction(d["direcao"]),
                quantidade=int(d["quantidade"]), preco_entrada=float(d["preco_entrada"]),
                preco_saida=float(d["preco_saida"]),
                aberta_em=_dt.fromisoformat(d["aberta_em"]),
                fechada_em=_dt.fromisoformat(d["fechada_em"]),
                custos=float(d.get("custos", 0.0)), motivo=d.get("motivo", ""),
            ))
        return broker
