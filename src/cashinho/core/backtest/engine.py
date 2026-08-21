"""O motor de backtest.

**A regra que sustenta o resultado**: uma estrategia que decide no fechamento
do candle so pode ser executada a partir do candle SEGUINTE. O engine respeita
isso pela propria ordem das etapas dentro de cada candle:

    candle i chega
      0. saida pendente (decidida no fechamento de i-1) executa na ABERTURA de i
      1. entrada pendente (decidida no fechamento de i-1) executa na ABERTURA de i
      2. stop e alvo sao testados contra a maxima e a minima de i
      3. horario de encerramento zera a posicao
      -- candle i FECHA --
      4. so agora a estrategia olha os dados e pode gerar uma ordem, que fica
         pendente para o candle i+1
      5. o patrimonio e' marcado a mercado

Nenhuma etapa enxerga um preco que ainda nao aconteceu. Quando stop e alvo
cabem dentro do mesmo candle, o engine nao tem como saber qual veio primeiro:
por padrao assume o **stop** (``prioridade_intracandle="stop"``), que e' a
hipotese pessimista.

O engine nao depende de interface nenhuma: recebe serie e estrategia, devolve
:class:`BacktestResult`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from ...models import BRT, Candle, Direction, Series
from ..mtf import MTFConfig, MTFEngine
from ..mtf.timeframes import rotulo_canonico
from ..risk import PedidoOperacao, RiskManager, RiskRejectionError, RiskState
from ..risk.models import RiskDecision
from ..strategy.base import Strategy
from ..strategy.context import StrategyContext
from ..strategy.models import Action, Signal
from .config import BacktestConfig
from .metrics import calcular
from .models import BacktestResult, BacktestTrade, MotivoSaida, PontoEquity


class _Aberta:
    """Posicao viva durante a simulacao."""

    __slots__ = ("symbol", "direcao", "quantidade", "preco", "stop", "alvo", "ts", "risco",
                 "setup", "confianca")

    def __init__(self, symbol, direcao, quantidade, preco, stop, alvo, ts, risco, setup, confianca):
        self.symbol = symbol
        self.direcao = direcao
        self.quantidade = quantidade
        self.preco = preco
        self.stop = stop
        self.alvo = alvo
        self.ts = ts
        self.risco = risco
        self.setup = setup
        self.confianca = confianca

    def pnl(self, preco: float) -> float:
        sinal = 1 if self.direcao is Direction.LONG else -1
        return (preco - self.preco) * self.quantidade * sinal


class _Pendente:
    """Ordem decidida no fechamento anterior, esperando a proxima abertura."""

    __slots__ = ("decisao", "sinal")

    def __init__(self, decisao: RiskDecision, sinal: Signal):
        self.decisao = decisao
        self.sinal = sinal


class BacktestEngine:
    """Simula a estrategia candle a candle, com custos, horario e risco."""

    def __init__(self, estrategia: Strategy, config: Optional[BacktestConfig] = None):
        self.estrategia = estrategia
        self.config = config or BacktestConfig()
        self._agora: datetime = datetime.now(BRT)

    # ------------------------------------------------------------------
    def rodar(self, serie_base: Series) -> BacktestResult:
        c = self.config
        symbol = c.symbol or serie_base.symbol
        tf_base = rotulo_canonico(c.timeframe_base)
        tf_setup = rotulo_canonico(c.timeframe_setup)

        mtf = MTFEngine(
            MTFConfig(
                base=tf_base,
                camadas={"setup": tf_setup, "gatilho": tf_base},
                sessao=c.sessao,
            ),
            symbol=symbol,
        ).alimentar(serie_base)

        risco = RiskManager(
            c.risco,
            RiskState(capital_inicial=c.capital_inicial),
            relogio=lambda: self._agora,
        )

        trades: list[BacktestTrade] = []
        equity: list[PontoEquity] = []
        rejeicoes: dict[str, int] = {}
        avisos: list[str] = []

        aberta: Optional[_Aberta] = None
        pendente: Optional[_Pendente] = None
        saida_pendente: Optional[MotivoSaida] = None
        dia_atual: Optional[date] = None
        setup_visto = 0
        sinais = 0
        acionaveis = 0

        barras = [b for b in mtf.barras(tf_base) if c.dentro_do_periodo(b.inicio.date())]
        if not barras:
            avisos.append("nenhum candle no periodo pedido")

        # ultimo candle de cada pregao: day trade nao dorme posicionado, mesmo
        # quando a serie termina antes do horario configurado em fechar_em
        ultimo_do_dia = {b.inicio.date(): i for i, b in enumerate(barras)}

        for indice, barra in enumerate(barras):
            candle: Candle = barra.candle
            self._agora = candle.ts
            dia = candle.ts.date()

            # --- virada de pregao ---------------------------------------
            if dia != dia_atual:
                if aberta is not None:  # dado com buraco: nao ha como segurar overnight
                    trades.append(self._encerrar(risco, aberta, candle.open, candle.ts,
                                                 MotivoSaida.FIM_DO_DIA))
                    aberta = None
                    avisos.append(f"posicao encerrada na virada para {dia:%d/%m}")
                risco.novo_pregao(dia)
                dia_atual = dia
                pendente = None
                saida_pendente = None

            # --- 0) saida decidida no fechamento anterior ----------------
            if aberta is not None and saida_pendente is not None:
                trades.append(self._encerrar(risco, aberta, candle.open, candle.ts, saida_pendente))
                aberta = None
                saida_pendente = None

            # --- 1) entrada pendente executa na abertura -----------------
            if pendente is not None and aberta is None:
                aberta = self._abrir(risco, pendente, candle, rejeicoes)
                pendente = None

            # --- 2) stop e alvo dentro do candle -------------------------
            if aberta is not None:
                saida = self._saida_intracandle(aberta, candle)
                if saida is not None:
                    preco, motivo = saida
                    trades.append(self._encerrar(risco, aberta, preco, candle.ts, motivo,
                                                 ordem_limitada=motivo is MotivoSaida.ALVO))
                    aberta = None

            # --- 3) horario de encerramento -------------------------------
            fim_do_pregao = ultimo_do_dia.get(dia) == indice
            if aberta is not None and (self._passou_do_horario(candle.ts) or fim_do_pregao):
                trades.append(self._encerrar(risco, aberta, candle.close, candle.ts,
                                             MotivoSaida.FIM_DO_DIA))
                aberta = None

            # --- 4) o candle FECHOU: agora a estrategia pode agir ---------
            vista = mtf.em(barra.fim)
            fechados = len(vista.barras_fechadas(tf_setup))
            if fechados > setup_visto:
                setup_visto = fechados
                sinal = self._avaliar(vista, symbol, tf_setup)
                if sinal is not None:
                    sinais += 1
                    if sinal.action.acionavel:
                        acionaveis += 1
                    if aberta is not None and c.sair_no_sinal_contrario:
                        if sinal.action.acionavel and sinal.action.direcao is not aberta.direcao:
                            saida_pendente = MotivoSaida.SINAL_CONTRARIO
                    elif aberta is None and pendente is None:
                        pendente = self._decidir(risco, sinal, barra.fim, rejeicoes)

            # --- 5) marcacao a mercado ------------------------------------
            equity.append(self._ponto(risco, aberta, candle))

        # --- fim da serie: nao existe trade em aberto no resultado ---------
        if aberta is not None and barras:
            ultimo = barras[-1].candle
            trades.append(self._encerrar(risco, aberta, ultimo.close, ultimo.ts,
                                         MotivoSaida.FIM_DOS_DADOS))
            avisos.append("a serie terminou com posicao aberta; ela foi encerrada no ultimo preco")
            equity[-1] = self._ponto(risco, None, ultimo)

        metricas = calcular(trades, equity, c.capital_inicial)
        if 0 < metricas.dias < 20:
            avisos.append(
                f"apenas {metricas.dias} pregao(oes) no periodo: Sharpe, Sortino e drawdown "
                "sao pouco confiaveis com tao poucos dias"
            )
        if metricas.n_trades < 30:
            avisos.append(
                f"{metricas.n_trades} trade(s): amostra pequena demais para concluir "
                "qualquer coisa sobre a estrategia"
            )

        capital_final = equity[-1].equity if equity else c.capital_inicial
        resultado = BacktestResult(
            symbol=symbol,
            timeframe=f"{tf_setup} (execucao em {tf_base})",
            estrategia=self.estrategia.nome,
            capital_inicial=c.capital_inicial,
            capital_final=capital_final,
            inicio=barras[0].candle.ts if barras else None,
            fim=barras[-1].candle.ts if barras else None,
            trades=trades,
            equity=equity,
            metricas=metricas,
            sinais_avaliados=sinais,
            sinais_acionaveis=acionaveis,
            rejeicoes_do_risco=rejeicoes,
            avisos=avisos,
            experimental=getattr(self.estrategia, "experimental", True),
        )
        return resultado

    # ------------------------------------------------------------------
    # etapas
    # ------------------------------------------------------------------
    def _avaliar(self, vista, symbol: str, tf_setup: str) -> Optional[Signal]:
        try:
            serie = vista.fechados(tf_setup)
            if len(serie) == 0:
                return None
            contexto = StrategyContext(symbol=symbol, serie=serie)
        except ValueError:
            return None
        return self.estrategia.avaliar(contexto)

    def _decidir(self, risco: RiskManager, sinal: Signal, instante: datetime,
                 rejeicoes: dict[str, int]) -> Optional[_Pendente]:
        c = self.config
        if not sinal.action.acionavel:
            return None
        if sinal.action is Action.SELL and not c.permitir_venda:
            return None
        if c.entrada_ate and instante.astimezone(BRT).time() >= c.entrada_ate:
            rejeicoes["fora_do_horario_de_entrada"] = rejeicoes.get("fora_do_horario_de_entrada", 0) + 1
            return None

        niveis = sinal.niveis
        if "entrada_referencia" not in niveis or "stop_referencia" not in niveis:
            rejeicoes["sinal_sem_niveis"] = rejeicoes.get("sinal_sem_niveis", 0) + 1
            return None

        decisao = risco.avaliar(
            PedidoOperacao(
                symbol=sinal.symbol,
                direcao=sinal.action.direcao,
                entrada=niveis["entrada_referencia"],
                stop=niveis["stop_referencia"],
                alvo=niveis.get("alvo_referencia"),
                referencia=sinal.strategy,
            )
        )
        if not decisao.allowed:
            for r in decisao.rejeicoes:
                rejeicoes[r.codigo.value] = rejeicoes.get(r.codigo.value, 0) + 1
            return None
        return _Pendente(decisao, sinal)

    def _abrir(self, risco: RiskManager, pendente: _Pendente, candle: Candle,
               rejeicoes: dict[str, int]) -> Optional[_Aberta]:
        c = self.config
        decisao, sinal = pendente.decisao, pendente.sinal
        direcao = decisao.direcao
        preco = c.custos.preco_execucao(candle.open, direcao, entrando=True)
        try:
            risco.abrir(decisao, preco_execucao=preco)
        except RiskRejectionError:
            rejeicoes["bloqueado_na_execucao"] = rejeicoes.get("bloqueado_na_execucao", 0) + 1
            return None
        return _Aberta(
            symbol=decisao.symbol,
            direcao=direcao,
            quantidade=decisao.position_size,
            preco=preco,
            stop=decisao.stop,
            alvo=sinal.niveis.get("alvo_referencia", 0.0),
            ts=candle.ts,
            risco=decisao.monetary_risk,
            setup=sinal.setup,
            confianca=sinal.confidence,
        )

    def _saida_intracandle(self, aberta: _Aberta, candle: Candle) -> Optional[tuple[float, MotivoSaida]]:
        """Stop e alvo testados contra a maxima e a minima - com gap tratado.

        Se o candle ABRE alem do nivel, a execucao sai na abertura (e' o que
        acontece de verdade num gap), e nao no preco do nivel.
        """
        alta = aberta.direcao is Direction.LONG
        stop, alvo = aberta.stop, aberta.alvo

        if alta:
            bateu_stop = candle.low <= stop
            preco_stop = candle.open if candle.open <= stop else stop
            bateu_alvo = bool(alvo) and candle.high >= alvo
            preco_alvo = candle.open if (alvo and candle.open >= alvo) else alvo
        else:
            bateu_stop = candle.high >= stop
            preco_stop = candle.open if candle.open >= stop else stop
            bateu_alvo = bool(alvo) and candle.low <= alvo
            preco_alvo = candle.open if (alvo and candle.open <= alvo) else alvo

        if bateu_stop and bateu_alvo:
            prioridade = self.config.prioridade_intracandle
            if prioridade == "alvo":
                return preco_alvo, MotivoSaida.ALVO
            if prioridade == "nenhuma":
                return None  # nao da para decidir: segura a posicao mais um candle
            return preco_stop, MotivoSaida.STOP  # pessimista, o padrao
        if bateu_stop:
            return preco_stop, MotivoSaida.STOP
        if bateu_alvo:
            return preco_alvo, MotivoSaida.ALVO
        return None

    def _encerrar(self, risco: RiskManager, aberta: _Aberta, preco_base: float,
                  ts: datetime, motivo: MotivoSaida, ordem_limitada: bool = False) -> BacktestTrade:
        c = self.config
        preco = c.custos.preco_execucao(preco_base, aberta.direcao, entrando=False,
                                        ordem_limitada=ordem_limitada)
        custos = c.custos.custo_total(aberta.quantidade, aberta.preco, preco)
        self._agora = ts
        risco.fechar(aberta.symbol, preco, custos=custos)
        return BacktestTrade(
            symbol=aberta.symbol,
            direcao=aberta.direcao,
            quantidade=aberta.quantidade,
            entrada_em=aberta.ts,
            entrada_preco=aberta.preco,
            saida_em=ts,
            saida_preco=preco,
            motivo=motivo,
            custos=custos,
            stop=aberta.stop,
            alvo=aberta.alvo,
            risco_planejado=aberta.risco,
            setup=aberta.setup,
            confianca=aberta.confianca,
        )

    def _passou_do_horario(self, ts: datetime) -> bool:
        limite = self.config.fechar_em
        return bool(limite) and ts.astimezone(BRT).time() >= limite

    def _ponto(self, risco: RiskManager, aberta: Optional[_Aberta], candle: Candle) -> PontoEquity:
        realizado = risco.estado.patrimonio
        aberto = aberta.pnl(candle.close) if aberta else 0.0
        exposicao = aberta.quantidade * candle.close if aberta else 0.0
        return PontoEquity(
            ts=candle.ts,
            equity=realizado + aberto,
            realizado=realizado,
            aberto=aberto,
            exposicao=exposicao,
            posicionado=aberta is not None,
        )
