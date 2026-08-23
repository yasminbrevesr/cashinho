"""Oportunidades e contextos de auditoria montados a mao."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.auditor.checagens import ConfigAuditor, ContextoAuditoria
from cashinho.core.confluencia.estados import (
    ContextState,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
)
from cashinho.core.confluencia.modelos import (
    Context,
    LeituraMultiTimeframe,
    Setup,
    Trend,
    Trigger,
)
from cashinho.core.oportunidade.estados import EstadoOportunidade
from cashinho.core.oportunidade.modelos import Opportunity
from cashinho.core.structure.models import (
    EventoEstrutura,
    Level,
    MarketStructure,
    Pivot,
    Regime,
    Tendencia,
    TipoEvento,
    TipoPivo,
)
from cashinho.models import BRT, Candle, Direction, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)
AGORA = ABERTURA + timedelta(hours=2, minutes=37)


def leitura(
    context: Optional[ContextState] = ContextState.BULLISH,
    trend: Optional[TrendState] = TrendState.BULLISH,
    setup: SetupState = SetupState.PULLBACK,
    trigger: TriggerState = TriggerState.BREAKOUT_WITH_VOLUME,
    vies: Vies = Vies.BULLISH,
    instante: datetime = AGORA,
) -> LeituraMultiTimeframe:
    camadas = []
    if context is not None:
        f = instante - timedelta(minutes=37)
        camadas.append(Context("context", "60m", context, f - timedelta(minutes=60), f,
                               instante, 0.8, ("contexto",), {}))
    if trend is not None:
        f = instante - timedelta(minutes=7)
        camadas.append(Trend("trend", "15m", trend, f - timedelta(minutes=15), f,
                             instante, 0.8, ("tendencia",), {}))
    f = instante - timedelta(minutes=2)
    camadas.append(Setup("setup", "5m", setup, f - timedelta(minutes=5), f, instante,
                         0.8, ("setup",), {"vies": vies.value}))
    camadas.append(Trigger("trigger", "1m", trigger, instante - timedelta(minutes=1),
                           instante, instante, 0.8, ("gatilho",), {"vies": vies.value}))
    return LeituraMultiTimeframe("PETR4", instante, tuple(camadas), ())


def oportunidade(
    direction: Direction = Direction.LONG,
    entry: float = 31.00,
    stop: float = 30.70,
    target: float = 31.60,
    score: float = 75.0,
    estado: EstadoOportunidade = EstadoOportunidade.APROVADO,
    expires_at: Optional[datetime] = None,
    instante: datetime = AGORA,
    **campos_leitura,
) -> Opportunity:
    risco = abs(entry - stop)
    return Opportunity(
        symbol="PETR4",
        timestamp=instante,
        direction=direction,
        setup="pullback a favor da tendencia",
        score=score,
        entry=entry, stop=stop, target=target,
        risk_reward=round(abs(target - entry) / risco, 3) if risco else 0.0,
        timeframe_context="60m", timeframe_trend="15m",
        timeframe_setup="5m", timeframe_trigger="1m",
        reasons=("teste",), warnings=(), invalidation="-",
        expires_at=expires_at if expires_at is not None else instante + timedelta(minutes=3),
        estado=estado,
        leitura=leitura(instante=instante, **campos_leitura),
    )


def nivel(low: float, high: float, tipo: str, toques: int = 2, forca: float = 0.7) -> Level:
    return Level(low=low, high=high, tipo=tipo, toques=toques, forca=forca, ultimo_toque=AGORA)


def estrutura(
    preco: float = 31.00,
    atr: float = 0.20,
    suportes: Sequence[Level] = (),
    resistencias: Sequence[Level] = (),
    regime: Regime = Regime.ALTA,
    swing_highs: Sequence[Pivot] = (),
    swing_lows: Sequence[Pivot] = (),
    eventos: Sequence[EventoEstrutura] = (),
) -> MarketStructure:
    return MarketStructure(
        symbol="PETR4", timeframe="5m", ts=AGORA, preco=preco, atr=atr,
        pivos=list(swing_highs) + list(swing_lows),
        swing_highs=list(swing_highs), swing_lows=list(swing_lows), swings=[],
        tendencia=Tendencia(regime, 0.7, "HH/HL", "tendencia de teste"),
        suportes=list(suportes), resistencias=list(resistencias),
        eventos=list(eventos),
    )


def pivo(indice: int, preco: float, tipo: TipoPivo = TipoPivo.TOPO) -> Pivot:
    return Pivot(indice=indice, ts=ABERTURA + timedelta(minutes=5 * indice), preco=preco,
                 tipo=tipo, indice_confirmacao=indice + 2,
                 ts_confirmacao=ABERTURA + timedelta(minutes=5 * (indice + 2)),
                 significativo=True)


def evento(tipo: TipoEvento, direcao: Direction, forca: float = 0.7) -> EventoEstrutura:
    return EventoEstrutura(tipo=tipo, direcao=direcao, ts=AGORA, indice=50, preco=31.0,
                           forca=forca, descricao=f"{tipo.value} de teste")


def serie(closes: Sequence[float], timeframe: str = "5m",
          volumes: Optional[Sequence[float]] = None) -> Series:
    candles = []
    anterior = closes[0]
    for i, c in enumerate(closes):
        candles.append(Candle(ABERTURA + timedelta(minutes=5 * i), anterior,
                              max(anterior, c) * 1.002, min(anterior, c) * 0.998, c,
                              volumes[i] if volumes else 10_000.0))
        anterior = c
    return Series("PETR4", timeframe, candles)


def contexto(
    op: Optional[Opportunity] = None,
    est: Optional[MarketStructure] = None,
    serie_setup: Optional[Series] = None,
    serie_trigger: Optional[Series] = None,
    agora: datetime = AGORA,
    cfg: Optional[ConfigAuditor] = None,
) -> ContextoAuditoria:
    return ContextoAuditoria(
        op=op or oportunidade(),
        agora=agora,
        cfg=cfg or ConfigAuditor(),
        estrutura=est if est is not None else estrutura(),
        serie_setup=serie_setup if serie_setup is not None else serie([31.0] * 60),
        serie_trigger=serie_trigger if serie_trigger is not None else serie(
            [31.0] * 60, timeframe="1m"
        ),
    )
