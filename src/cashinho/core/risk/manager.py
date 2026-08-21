"""O Risk Manager.

Independente de estrategia por construcao: a unica entrada e' um
:class:`PedidoOperacao` com ativo, direcao, entrada e stop. Nao ha campo para
setup, score, indicador ou "confianca" - nada que permita a uma estrategia
argumentar com o risco.

A decisao e' final:

- :class:`RiskDecision` e' congelada (nao da para virar ``allowed=True``);
- :meth:`RiskManager.abrir` so aceita uma decisao **emitida e aprovada por
  este gerente**, identificada por um id de uso unico - decisao forjada,
  reaproveitada ou de outro gerente e' recusada;
- antes de abrir, os bloqueios sao reavaliados: se algo mudou entre a analise
  e a execucao (kill switch acionado, limite estourado), a ordem nao passa.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Callable, Optional

from ...models import BRT, Direction
from .config import PADRAO, RiskConfig
from .models import (
    KillSwitch,
    LimiteUso,
    Limitador,
    MotivoRejeicao,
    PedidoOperacao,
    Position,
    Rejeicao,
    RiskDecision,
    RiskRejectionError,
    RiskStatus,
    TradeResult,
)
from .sizing import dimensionar
from .state import RiskState

_LIMITADOR_PARA_REJEICAO = {
    Limitador.RISCO: MotivoRejeicao.RISCO_INSUFICIENTE,
    Limitador.RISCO_DIARIO: MotivoRejeicao.RISCO_INSUFICIENTE,
    Limitador.CAPITAL: MotivoRejeicao.CAPITAL_INSUFICIENTE,
    Limitador.EXPOSICAO_ATIVO: MotivoRejeicao.EXPOSICAO_ATIVO,
    Limitador.EXPOSICAO_TOTAL: MotivoRejeicao.EXPOSICAO_TOTAL,
}


def _dinheiro(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class RiskManager:
    """Guarda-costas do capital. Diz sim, diz nao, e nao muda de ideia."""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        estado: Optional[RiskState] = None,
        relogio: Optional[Callable[[], datetime]] = None,
    ):
        self.config = config or PADRAO
        self.estado = estado or RiskState(capital_inicial=self.config.capital)
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self._aprovadas: dict[str, RiskDecision] = {}

    # ------------------------------------------------------------------
    # limites de estado (independem do pedido)
    # ------------------------------------------------------------------
    def bloqueios(self) -> list[Rejeicao]:
        """Motivos que impedem QUALQUER operacao agora."""
        e, c = self.estado, self.config
        fora: list[Rejeicao] = []

        if e.kill_switch is not None:
            fora.append(
                Rejeicao(
                    MotivoRejeicao.KILL_SWITCH,
                    f"kill switch acionado ({e.kill_switch.codigo}): {e.kill_switch.motivo}",
                )
            )

        limite_dia = c.perda_max_diaria(e.capital_pregao)
        if e.pnl_dia <= -limite_dia:
            fora.append(
                Rejeicao(
                    MotivoRejeicao.PERDA_DIARIA,
                    f"perda do dia {_dinheiro(-e.pnl_dia)} atingiu o limite de {_dinheiro(limite_dia)}",
                )
            )

        limite_dd = c.drawdown_max(e.pico)
        if e.drawdown >= limite_dd:
            fora.append(
                Rejeicao(
                    MotivoRejeicao.DRAWDOWN,
                    f"drawdown de {_dinheiro(e.drawdown)} ({e.drawdown_pct:.1f}%) atingiu o "
                    f"maximo de {c.drawdown_max_pct:.1f}%",
                )
            )

        if e.perdas_consecutivas >= c.max_perdas_consecutivas:
            fora.append(
                Rejeicao(
                    MotivoRejeicao.PERDAS_CONSECUTIVAS,
                    f"{e.perdas_consecutivas} perdas seguidas (maximo {c.max_perdas_consecutivas})",
                )
            )

        if e.trades_dia >= c.max_trades_dia:
            fora.append(
                Rejeicao(
                    MotivoRejeicao.MAX_TRADES,
                    f"{e.trades_dia} trades hoje (maximo {c.max_trades_dia})",
                )
            )

        return fora

    @property
    def liberado(self) -> bool:
        return not self.bloqueios()

    # ------------------------------------------------------------------
    # avaliacao
    # ------------------------------------------------------------------
    def avaliar(self, pedido: PedidoOperacao) -> RiskDecision:
        """Avalia um pedido e devolve a decisao. Nao altera o estado."""
        agora = self._relogio()
        e, c = self.estado, self.config
        exposicao_atual = e.exposicao_total()

        rejeicoes = self._validar_pedido(pedido)
        rejeicoes.extend(self.bloqueios())

        if not rejeicoes and not c.permitir_piramide and e.tem_posicao(pedido.symbol):
            rejeicoes.append(
                Rejeicao(
                    MotivoRejeicao.POSICAO_EXISTENTE,
                    f"ja existe posicao aberta em {pedido.symbol.upper()} e piramide esta desligada",
                )
            )

        if rejeicoes:
            return self._rejeitar(pedido, rejeicoes, exposicao_atual, agora)

        # risco alvo: o menor entre o risco por trade e o que ainda resta do dia
        risco_normal = c.risco_alvo(e.patrimonio)
        restante_dia = c.perda_max_diaria(e.capital_pregao) + min(e.pnl_dia, 0.0)
        risco_alvo = min(risco_normal, max(restante_dia, 0.0))
        limitador_risco = Limitador.RISCO_DIARIO if restante_dia < risco_normal else Limitador.RISCO

        dim = dimensionar(
            entrada=pedido.entrada,
            stop=pedido.stop,
            risco_alvo=risco_alvo,
            caixa_disponivel=e.caixa_disponivel(),
            teto_ativo_restante=c.teto_exposicao_ativo(e.patrimonio) - e.exposicao_de(pedido.symbol),
            teto_total_restante=c.teto_exposicao_total(e.patrimonio) - exposicao_atual,
            lote=c.lote,
            permitir_fracionario=c.permitir_fracionario,
            limitador_do_risco=limitador_risco,
        )

        if dim.zerado:
            return self._rejeitar(
                pedido, [self._rejeicao_de_tamanho(dim, pedido)], exposicao_atual, agora
            )

        exposicao_final = exposicao_atual + dim.exposicao
        decisao = RiskDecision(
            allowed=True,
            reason=(
                f"aprovado: {dim.quantidade} acoes, risco de {_dinheiro(dim.risco_efetivo)} "
                f"({dim.risco_efetivo / e.patrimonio * 100:.2f}% do patrimonio), "
                f"tamanho limitado por {dim.limitador.value}"
            ),
            position_size=dim.quantidade,
            monetary_risk=dim.risco_efetivo,
            portfolio_exposure=exposicao_final,
            symbol=pedido.symbol.upper(),
            direcao=pedido.direcao,
            entrada=pedido.entrada,
            stop=pedido.stop,
            risco_por_acao=dim.risco_por_acao,
            risco_alvo=risco_alvo,
            exposicao_da_ordem=dim.exposicao,
            exposicao_pct=(exposicao_final / e.patrimonio * 100.0) if e.patrimonio else 0.0,
            limitador=dim.limitador,
            avaliado_em=agora,
            id=uuid.uuid4().hex,
        )
        self._aprovadas[decisao.id] = decisao
        return decisao

    def _validar_pedido(self, pedido: PedidoOperacao) -> list[Rejeicao]:
        problemas: list[str] = []
        if not pedido.symbol or not pedido.symbol.strip():
            problemas.append("ativo nao informado")
        if pedido.entrada <= 0:
            problemas.append(f"entrada invalida ({pedido.entrada})")
        if pedido.stop <= 0:
            problemas.append(f"stop invalido ({pedido.stop})")
        if pedido.entrada > 0 and pedido.stop > 0:
            if pedido.risco_por_acao <= 0:
                problemas.append("entrada e stop no mesmo preco: risco por acao seria zero")
            elif not pedido.stop_coerente:
                lado = "abaixo" if pedido.direcao is Direction.LONG else "acima"
                problemas.append(
                    f"stop do lado errado: em {pedido.direcao.value.lower()} o stop fica {lado} da entrada"
                )
        if not problemas:
            return []
        return [Rejeicao(MotivoRejeicao.ORDEM_INVALIDA, "; ".join(problemas))]

    def _rejeicao_de_tamanho(self, dim, pedido: PedidoOperacao) -> Rejeicao:
        codigo = _LIMITADOR_PARA_REJEICAO[dim.limitador]
        bruto = dim.candidatos.get(dim.limitador.name, 0)
        if codigo is MotivoRejeicao.RISCO_INSUFICIENTE and bruto > 0:
            return Rejeicao(
                MotivoRejeicao.RISCO_INSUFICIENTE,
                f"o risco permitido compra {bruto} acoes, menos que o lote padrao "
                f"({self.config.lote}) e o fracionario esta desligado",
            )
        return Rejeicao(
            codigo,
            f"quantidade calculada ficou em zero: {dim.limitador.value} nao comporta nem "
            f"1 acao de {pedido.symbol.upper()} a {_dinheiro(pedido.entrada)}",
        )

    def _rejeitar(
        self,
        pedido: PedidoOperacao,
        rejeicoes: list[Rejeicao],
        exposicao_atual: float,
        agora: datetime,
    ) -> RiskDecision:
        return RiskDecision(
            allowed=False,
            reason=rejeicoes[0].mensagem,
            position_size=0,
            monetary_risk=0.0,
            portfolio_exposure=exposicao_atual,
            symbol=pedido.symbol.upper(),
            direcao=pedido.direcao,
            entrada=pedido.entrada,
            stop=pedido.stop,
            risco_por_acao=pedido.risco_por_acao,
            exposicao_pct=(exposicao_atual / self.estado.patrimonio * 100.0)
            if self.estado.patrimonio
            else 0.0,
            rejeicoes=tuple(rejeicoes),
            avaliado_em=agora,
            id="",
        )

    # ------------------------------------------------------------------
    # execucao
    # ------------------------------------------------------------------
    def abrir(self, decisao: RiskDecision, preco_execucao: Optional[float] = None) -> Position:
        """Registra a posicao. So aceita decisao aprovada emitida por este gerente."""
        if decisao.rejeitada:
            raise RiskRejectionError(f"operacao rejeitada pelo risco: {decisao.reason}")

        # os bloqueios sao reavaliados antes do id: se algo travou entre a
        # analise e a execucao, o motivo util e' o bloqueio, nao o id
        bloqueios = self.bloqueios()
        if bloqueios:
            self._aprovadas.pop(decisao.id, None)
            raise RiskRejectionError(
                f"o risco mudou entre a analise e a execucao: {bloqueios[0].mensagem}"
            )

        if not decisao.id or decisao.id not in self._aprovadas:
            raise RiskRejectionError(
                "decisao nao reconhecida: so decisoes emitidas por este Risk Manager "
                "(e ainda nao usadas) podem abrir posicao"
            )
        self._aprovadas.pop(decisao.id)
        posicao = Position(
            symbol=decisao.symbol,
            direcao=decisao.direcao,
            quantidade=decisao.position_size,
            preco_medio=preco_execucao if preco_execucao is not None else decisao.entrada,
            stop=decisao.stop,
            aberta_em=self._relogio(),
            decisao_id=decisao.id,
        )
        self.estado.registrar_abertura(posicao)
        return posicao

    def fechar(
        self, symbol: str, preco_saida: float, custos: Optional[float] = None
    ) -> TradeResult:
        """Fecha a posicao, contabiliza o resultado e reavalia as travas."""
        chave = symbol.upper()
        posicao = self.estado.posicoes.get(chave)
        if posicao is None:
            raise KeyError(f"nao ha posicao aberta em {chave}")

        trade = TradeResult(
            symbol=chave,
            direcao=posicao.direcao,
            quantidade=posicao.quantidade,
            preco_entrada=posicao.preco_medio,
            preco_saida=preco_saida,
            custos=self.config.custo_por_trade if custos is None else custos,
            aberto_em=posicao.aberta_em,
            fechado_em=self._relogio(),
        )
        self.estado.registrar_fechamento(trade)
        self._avaliar_travas_automaticas()
        return trade

    def _avaliar_travas_automaticas(self) -> None:
        """Arma o kill switch sozinho quando um limite duro e' atingido."""
        if self.estado.kill_switch is not None:
            return
        e, c = self.estado, self.config

        limite_dia = c.perda_max_diaria(e.capital_pregao)
        if e.pnl_dia <= -limite_dia:
            self._armar(
                "perda_diaria",
                f"perda do dia {_dinheiro(-e.pnl_dia)} atingiu o limite de {_dinheiro(limite_dia)}",
                diario=True,
            )
            return
        if e.drawdown >= c.drawdown_max(e.pico):
            self._armar(
                "drawdown",
                f"drawdown de {e.drawdown_pct:.1f}% atingiu o maximo de {c.drawdown_max_pct:.1f}%",
                diario=False,
            )
            return
        if e.perdas_consecutivas >= c.max_perdas_consecutivas:
            self._armar(
                "perdas_consecutivas",
                f"{e.perdas_consecutivas} perdas seguidas (maximo {c.max_perdas_consecutivas})",
                diario=True,
            )

    def _armar(self, codigo: str, motivo: str, diario: bool) -> None:
        self.estado.kill_switch = KillSwitch(
            codigo=codigo, motivo=motivo, acionado_em=self._relogio(), diario=diario
        )
        self._aprovadas.clear()  # decisoes pendentes morrem junto

    # ------------------------------------------------------------------
    # kill switch e pregao
    # ------------------------------------------------------------------
    def acionar_kill_switch(self, motivo: str = "acionado manualmente") -> KillSwitch:
        self._armar("manual", motivo, diario=False)
        return self.estado.kill_switch

    def liberar_kill_switch(self) -> None:
        """Desarma a trava. E' deliberadamente manual - nada libera sozinho."""
        self.estado.kill_switch = None

    def novo_pregao(self, dia: Optional[date] = None) -> None:
        self.estado.novo_pregao(dia)
        self._aprovadas.clear()

    def atualizar_config(self, **campos) -> RiskConfig:
        """Troca limites em tempo real (e' o que a pagina de risco usa)."""
        nova = self.config.atualizar(**campos)
        if "capital" in campos:
            self.estado.ajustar_capital(nova.capital)
        self.config = nova
        self._aprovadas.clear()  # limites novos invalidam decisoes ja emitidas
        return nova

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def status(self) -> RiskStatus:
        e, c = self.estado, self.config
        bloqueios = self.bloqueios()
        exposicao = e.exposicao_total()
        return RiskStatus(
            liberado=not bloqueios,
            motivos=[r.mensagem for r in bloqueios],
            capital=c.capital,
            patrimonio=e.patrimonio,
            capital_pregao=e.capital_pregao,
            pnl_dia=e.pnl_dia,
            trades_dia=e.trades_dia,
            perdas_consecutivas=e.perdas_consecutivas,
            drawdown=e.drawdown,
            drawdown_pct=e.drawdown_pct,
            exposicao_total=exposicao,
            exposicao_pct=(exposicao / e.patrimonio * 100.0) if e.patrimonio else 0.0,
            posicoes=list(e.posicoes.values()),
            kill_switch=e.kill_switch,
            pregao=e.pregao,
            limites=[
                LimiteUso("perda do dia", abs(min(e.pnl_dia, 0.0)), c.perda_max_diaria(e.capital_pregao)),
                LimiteUso("trades no dia", e.trades_dia, c.max_trades_dia, "trades"),
                LimiteUso("perdas seguidas", e.perdas_consecutivas, c.max_perdas_consecutivas, "perdas"),
                LimiteUso("drawdown", e.drawdown, c.drawdown_max(e.pico)),
                LimiteUso("exposicao total", exposicao, c.teto_exposicao_total(e.patrimonio)),
            ],
        )
