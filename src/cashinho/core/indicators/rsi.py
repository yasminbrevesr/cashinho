"""Indice de Forca Relativa (Wilder)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashinho.core.indicators.base import (
    IndicatorResult,
    prepare,
    validate_period,
    wilder_smoothing,
)
from cashinho.domain.market import CandleSeries

DEFAULT_PERIOD = 14


def rsi(series: CandleSeries, period: int = DEFAULT_PERIOD, *, column: str = "close") -> IndicatorResult:
    """RSI com suavizacao de Wilder.

    Exige `period + 1` candles: o primeiro serve apenas para produzir a
    primeira variacao.

    Quando a media de perdas e zero (sequencia sem queda), a divisao
    tenderia ao infinito; o valor correto e 100 e e tratado
    explicitamente, nao deixado como inf.

    O indicador nao classifica sobrecompra ou sobrevenda: 70 e 30 sao
    convencao de leitura, nao regra do calculo, e transformar isso em
    sinal aqui violaria a separacao entre indicador e estrategia.
    """
    validate_period(period, minimum=2)
    frame = prepare(series, minimum=period + 1, indicator=f"RSI({period})")

    delta = frame[column].diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)

    avg_gain = wilder_smoothing(gains, period)
    avg_loss = wilder_smoothing(losses, period)

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    values = 100.0 - (100.0 / (1.0 + rs))
    values = values.where(avg_loss != 0.0, 100.0)
    values = values.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), 50.0)
    values[avg_gain.isna() | avg_loss.isna()] = np.nan

    return IndicatorResult(
        name=f"RSI({period})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame({f"rsi_{period}": values}),
        warmup=period,
        params={"period": float(period)},
    )
