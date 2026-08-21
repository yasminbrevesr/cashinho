"""Average True Range (Wilder)."""

from __future__ import annotations

import pandas as pd

from cashinho.core.indicators.base import (
    IndicatorResult,
    prepare,
    validate_period,
    wilder_smoothing,
)
from cashinho.domain.market import CandleSeries

DEFAULT_PERIOD = 14


def true_range(frame: pd.DataFrame) -> pd.Series:
    """True Range: maior entre amplitude do candle e os dois gaps.

    Considerar apenas `high - low` ignoraria gaps de abertura, que sao
    justamente onde o risco real aparece — e o ATR alimenta calculo de
    stop.
    """
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(series: CandleSeries, period: int = DEFAULT_PERIOD) -> IndicatorResult:
    """ATR com suavizacao de Wilder.

    Devolve tambem o True Range bruto: a distancia entre TR e ATR indica
    expansao ou contracao de volatilidade, informacao que se perderia se
    apenas a media fosse retornada.
    """
    validate_period(period, minimum=2)
    frame = prepare(series, minimum=period + 1, indicator=f"ATR({period})")

    tr = true_range(frame)
    # Sem fechamento anterior, o TR do primeiro candle e indefinido.
    # `wilder_smoothing` descarta o NaN e semeia na media dos `period`
    # primeiros TR validos, como no calculo original de Wilder.
    tr.iloc[0] = float("nan")
    values = wilder_smoothing(tr, period)

    return IndicatorResult(
        name=f"ATR({period})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame({f"atr_{period}": values, "true_range": tr}),
        warmup=period,
        params={"period": float(period)},
    )
