"""Oportunidades para os testes da boleta."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from cashinho.core.confluencia.estados import ContextState, SetupState, TrendState, TriggerState, Vies
from cashinho.core.confluencia.modelos import Context, LeituraMultiTimeframe, Setup, Trend, Trigger
from cashinho.core.oportunidade.estados import EstadoOportunidade
from cashinho.core.oportunidade.modelos import Opportunity
from cashinho.core.risk import PedidoOperacao, RiskConfig, RiskManager, RiskState
from cashinho.models import BRT, Direction

AGORA = datetime(2026, 8, 20, 12, 37, tzinfo=BRT)


def leitura(instante: datetime = AGORA) -> LeituraMultiTimeframe:
    f60 = instante - timedelta(minutes=37)
    f15 = instante - timedelta(minutes=7)
    f5 = instante - timedelta(minutes=2)
    return LeituraMultiTimeframe("PETR4", instante, (
        Context("context", "60m", ContextState.BULLISH, f60 - timedelta(minutes=60), f60,
                instante, 0.8, ("contexto",), {}),
        Trend("trend", "15m", TrendState.BULLISH, f15 - timedelta(minutes=15), f15,
              instante, 0.8, ("tendencia",), {}),
        Setup("setup", "5m", SetupState.PULLBACK, f5 - timedelta(minutes=5), f5, instante,
              0.8, ("setup",), {"vies": Vies.BULLISH.value}),
        Trigger("trigger", "1m", TriggerState.BREAKOUT_WITH_VOLUME,
                instante - timedelta(minutes=1), instante, instante, 0.8, ("gatilho",),
                {"vies": Vies.BULLISH.value}),
    ), ())


def oportunidade(
    direction: Direction = Direction.LONG,
    entry: float = 31.15,
    stop: float = 30.72,
    target: float = 32.01,
    score: float = 78.4,
    estado: EstadoOportunidade = EstadoOportunidade.APROVADO,
    com_leitura: bool = True,
    expira_em_min: Optional[int] = 3,
    instante: datetime = AGORA,
) -> Opportunity:
    risco = abs(entry - stop)
    return Opportunity(
        symbol="PETR4", timestamp=instante, direction=direction,
        setup="pullback a favor da tendencia", score=score,
        entry=entry, stop=stop, target=target,
        risk_reward=round(abs(target - entry) / risco, 3) if risco else 0.0,
        timeframe_context="60m", timeframe_trend="15m",
        timeframe_setup="5m", timeframe_trigger="1m",
        reasons=("60m bullish", "15m bullish"),
        warnings=("risco/retorno de 2.00: pouca margem para erro",),
        invalidation="perder R$ 30,72; a tendencia de 15m virar",
        expires_at=(instante + timedelta(minutes=expira_em_min)) if expira_em_min else None,
        estado=estado,
        leitura=leitura(instante) if com_leitura else None,
    )


def decisao(op: Optional[Opportunity] = None, capital: float = 100_000.0):
    op = op or oportunidade()
    rm = RiskManager(RiskConfig(capital=capital, risco_por_trade_pct=1.0),
                     RiskState(capital_inicial=capital))
    return rm.avaliar(PedidoOperacao(op.symbol, op.direction, op.entry, op.stop))
