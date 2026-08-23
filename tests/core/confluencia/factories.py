"""Series e vistas para os testes de confluencia."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.confluencia.engine import MultiTimeframeEngine
from cashinho.core.mtf import MTFConfig, MTFEngine
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)  # quinta


def serie_1m(
    closes: Sequence[float],
    volumes: Optional[Sequence[float]] = None,
    pavio: float = 0.0015,
    inicio: Optional[datetime] = None,
    symbol: str = "PETR4",
) -> Series:
    inicio = inicio or ABERTURA
    candles: list[Candle] = []
    anterior = closes[0]
    for i, fechamento in enumerate(closes):
        abertura = anterior
        topo = max(abertura, fechamento)
        base = min(abertura, fechamento)
        candles.append(
            Candle(
                ts=inicio + timedelta(minutes=i),
                open=abertura,
                high=topo * (1 + pavio),
                low=base * (1 - pavio),
                close=fechamento,
                volume=(volumes[i] if volumes else 10_000.0),
            )
        )
        anterior = fechamento
    return Series(symbol, "1m", candles)


def serie_alta(n: int = 400, passo: float = 0.0006) -> Series:
    return serie_1m([30.0 * (1 + passo) ** i for i in range(n)])


def serie_baixa(n: int = 400, passo: float = 0.0006) -> Series:
    return serie_1m([30.0 * (1 - passo) ** i for i in range(n)])


def serie_parada(n: int = 400) -> Series:
    return serie_1m([30.0] * n)


def motor(serie: Series, engine: Optional[MultiTimeframeEngine] = None) -> MTFEngine:
    engine = engine or MultiTimeframeEngine()
    return MTFEngine(engine.config, symbol=serie.symbol).alimentar(serie)


def vista_em(serie: Series, minutos: int, engine: Optional[MultiTimeframeEngine] = None):
    """Vista no fechamento do candle de 1m de indice ``minutos``."""
    m = motor(serie, engine)
    return m.em(ABERTURA + timedelta(minutes=minutos + 1))


# ---------------------------------------------------------------------------
# leituras montadas a mao (para testar regras sem depender de dados)
# ---------------------------------------------------------------------------

from cashinho.core.confluencia.estados import (  # noqa: E402
    ContextState,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
)
from cashinho.core.confluencia.modelos import (  # noqa: E402
    Context,
    LeituraMultiTimeframe,
    Setup,
    Trend,
    Trigger,
)

INSTANTE = ABERTURA + timedelta(hours=2, minutes=37)  # 12:37


def leitura(
    context: Optional[ContextState] = ContextState.BULLISH,
    trend: Optional[TrendState] = TrendState.BULLISH,
    setup: Optional[SetupState] = SetupState.PULLBACK,
    trigger: Optional[TriggerState] = TriggerState.BREAKOUT_WITH_VOLUME,
    vies_setup: Vies = Vies.BULLISH,
    vies_trigger: Vies = Vies.BULLISH,
    forca: float = 0.8,
    instante: Optional[datetime] = None,
    idade_context_min: float = 37.0,
    preco: float = 30.0,
    atr: float = 0.10,
) -> LeituraMultiTimeframe:
    """Uma leitura com os estados exatos que o teste quiser."""
    agora = instante or INSTANTE
    camadas = []
    faltando = []

    if context is not None:
        fechado = agora - timedelta(minutes=idade_context_min)
        camadas.append(Context("context", "60m", context, fechado - timedelta(minutes=60),
                               fechado, agora, forca, ("contexto de teste",), {"preco": preco}))
    else:
        faltando.append("context")

    if trend is not None:
        fechado = agora - timedelta(minutes=7)
        camadas.append(Trend("trend", "15m", trend, fechado - timedelta(minutes=15),
                             fechado, agora, forca, ("tendencia de teste",), {"preco": preco}))
    else:
        faltando.append("trend")

    if setup is not None:
        fechado = agora - timedelta(minutes=2)
        camadas.append(Setup("setup", "5m", setup, fechado - timedelta(minutes=5), fechado, agora,
                             forca, ("setup de teste",),
                             {"vies": vies_setup.value, "preco": preco, "atr": atr,
                              "suporte": preco - 0.20, "resistencia": preco + 0.20}))
    else:
        faltando.append("setup")

    if trigger is not None:
        fechado = agora
        camadas.append(Trigger("trigger", "1m", trigger, fechado - timedelta(minutes=1), fechado,
                               agora, forca, ("gatilho de teste",),
                               {"vies": vies_trigger.value, "preco": preco}))
    else:
        faltando.append("trigger")

    return LeituraMultiTimeframe("PETR4", agora, tuple(camadas), tuple(faltando))
