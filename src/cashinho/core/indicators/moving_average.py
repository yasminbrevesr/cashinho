"""Medias moveis simples e exponencial."""

from __future__ import annotations

import pandas as pd

from cashinho.core.indicators.base import (
    IndicatorResult,
    exponential_average,
    prepare,
    validate_period,
)
from cashinho.domain.market import CandleSeries

DEFAULT_SMA_PERIOD = 20
DEFAULT_EMA_PERIOD = 9


def sma(series: CandleSeries, period: int = DEFAULT_SMA_PERIOD, *, column: str = "close") -> IndicatorResult:
    """Media movel simples.

    Os primeiros `period - 1` valores ficam NaN por construcao. Nao sao
    preenchidos: um valor calculado sobre janela incompleta pareceria
    valido e nao seria.
    """
    validate_period(period)
    frame = prepare(series, minimum=period, indicator=f"SMA({period})")
    values = frame[column].rolling(window=period, min_periods=period).mean()
    return IndicatorResult(
        name=f"SMA({period})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame({f"sma_{period}": values}),
        warmup=period - 1,
        params={"period": float(period)},
    )


def ema(series: CandleSeries, period: int = DEFAULT_EMA_PERIOD, *, column: str = "close") -> IndicatorResult:
    """Media movel exponencial, fator 2/(period+1).

    Semente na SMA dos `period` primeiros valores, como nas plataformas
    de grafico. Ver `recursive_average` para o motivo.
    """
    validate_period(period)
    frame = prepare(series, minimum=period, indicator=f"EMA({period})")
    values = exponential_average(frame[column], period)
    return IndicatorResult(
        name=f"EMA({period})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame({f"ema_{period}": values}),
        warmup=period - 1,
        params={"period": float(period)},
    )
