"""Contextos de score e oportunidades montados a mao."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

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
from cashinho.core.oportunidade.score import ContextoScore, montar_contexto
from cashinho.core.structure import analisar_estrutura
from cashinho.models import BRT, Candle, Direction, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)
INSTANTE = ABERTURA + timedelta(hours=2, minutes=37)


def serie(
    closes: Sequence[float],
    timeframe: str = "5m",
    minutos: int = 5,
    volumes: Optional[Sequence[float]] = None,
    pavio: float = 0.002,
) -> Series:
    candles: list[Candle] = []
    anterior = closes[0]
    for i, fechamento in enumerate(closes):
        abertura = anterior
        candles.append(
            Candle(
                ts=ABERTURA + timedelta(minutes=minutos * i),
                open=abertura,
                high=max(abertura, fechamento) * (1 + pavio),
                low=min(abertura, fechamento) * (1 - pavio),
                close=fechamento,
                volume=(volumes[i] if volumes else 10_000.0),
            )
        )
        anterior = fechamento
    return Series("PETR4", timeframe, candles)


def serie_alta(n: int = 120, passo: float = 0.001, **kwargs) -> Series:
    return serie([30.0 * (1 + passo) ** i for i in range(n)], **kwargs)


def serie_baixa(n: int = 120, passo: float = 0.001, **kwargs) -> Series:
    return serie([30.0 * (1 - passo) ** i for i in range(n)], **kwargs)


def caminho(pontos: Sequence[float], passos: int = 8) -> list[float]:
    """Caminho linear entre os pontos - cria pivos nos vertices."""
    closes = [float(pontos[0])]
    for destino in pontos[1:]:
        origem = closes[-1]
        for k in range(1, passos + 1):
            closes.append(origem + (destino - origem) * k / passos)
    return closes


def serie_com_swings_de_alta(**kwargs) -> Series:
    """Topos e fundos ascendentes - a estrutura le tendencia de alta."""
    return serie(caminho([30.0, 30.8, 30.5, 31.5, 31.1, 32.3]), **kwargs)


def serie_com_swings_de_baixa(**kwargs) -> Series:
    """Topos e fundos descendentes."""
    return serie(caminho([32.3, 31.5, 31.8, 30.8, 31.1, 30.0]), **kwargs)


def leitura(
    context: Optional[ContextState] = ContextState.BULLISH,
    trend: Optional[TrendState] = TrendState.BULLISH,
    setup: Optional[SetupState] = SetupState.PULLBACK,
    trigger: Optional[TriggerState] = TriggerState.BREAKOUT_WITH_VOLUME,
    vies: Vies = Vies.BULLISH,
    forca: float = 0.8,
    instante: datetime = INSTANTE,
) -> LeituraMultiTimeframe:
    camadas = []
    faltando = []
    if context is not None:
        f = instante - timedelta(minutes=37)
        camadas.append(Context("context", "60m", context, f - timedelta(minutes=60), f,
                               instante, forca, ("contexto",), {}))
    else:
        faltando.append("context")
    if trend is not None:
        f = instante - timedelta(minutes=7)
        camadas.append(Trend("trend", "15m", trend, f - timedelta(minutes=15), f,
                             instante, forca, ("tendencia",), {}))
    else:
        faltando.append("trend")
    if setup is not None:
        f = instante - timedelta(minutes=2)
        camadas.append(Setup("setup", "5m", setup, f - timedelta(minutes=5), f, instante,
                             forca, ("setup",), {"vies": vies.value}))
    else:
        faltando.append("setup")
    if trigger is not None:
        camadas.append(Trigger("trigger", "1m", trigger, instante - timedelta(minutes=1),
                               instante, instante, forca, ("gatilho de teste",),
                               {"vies": vies.value}))
    else:
        faltando.append("trigger")
    return LeituraMultiTimeframe("PETR4", instante, tuple(camadas), tuple(faltando))


def contexto(
    direcao: Direction = Direction.LONG,
    serie_setup: Optional[Series] = None,
    serie_trigger: Optional[Series] = None,
    entry: float = 31.0,
    stop: float = 30.5,
    target: float = 32.0,
    **campos_leitura,
) -> ContextoScore:
    """Contexto de score pronto - os testes ajustam os campos que quiserem."""
    s_setup = serie_setup if serie_setup is not None else serie_alta()
    s_trigger = serie_trigger if serie_trigger is not None else serie_alta(
        n=60, timeframe="1m", minutos=1
    )
    return montar_contexto(
        direcao=direcao,
        leitura=leitura(**campos_leitura),
        estrutura=analisar_estrutura(s_setup),
        serie_setup=s_setup,
        serie_trigger=s_trigger,
        entry=entry, stop=stop, target=target,
    )
