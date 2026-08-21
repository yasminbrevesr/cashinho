"""MACD — convergencia e divergencia de medias moveis."""

from __future__ import annotations

import pandas as pd

from cashinho.core.indicators.base import (
    IndicatorResult,
    exponential_average,
    prepare,
    validate_period,
)
from cashinho.domain.market import CandleSeries

DEFAULT_FAST = 12
DEFAULT_SLOW = 26
DEFAULT_SIGNAL = 9


def macd(
    series: CandleSeries,
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    column: str = "close",
) -> IndicatorResult:
    """Linha MACD, linha de sinal e histograma.

    As tres linhas voltam no mesmo DataFrame para garantir alinhamento
    temporal por construcao: cruzamento calculado sobre series obtidas em
    chamadas separadas ficaria sujeito a desalinhamento silencioso.

    O cruzamento em si nao e avaliado aqui. `histogram > 0` e leitura de
    quem consome, nao conclusao do indicador.
    """
    validate_period(fast, name="fast", minimum=2)
    validate_period(slow, name="slow", minimum=2)
    validate_period(signal, name="signal", minimum=2)
    if fast >= slow:
        raise ValueError(f"fast ({fast}) deve ser menor que slow ({slow})")

    minimum = slow + signal
    frame = prepare(series, minimum=minimum, indicator=f"MACD({fast},{slow},{signal})")

    fast_ema = exponential_average(frame[column], fast)
    slow_ema = exponential_average(frame[column], slow)
    macd_line = fast_ema - slow_ema
    signal_line = exponential_average(macd_line, signal)

    return IndicatorResult(
        name=f"MACD({fast},{slow},{signal})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame(
            {
                "macd": macd_line,
                "signal": signal_line,
                "histogram": macd_line - signal_line,
            }
        ),
        warmup=slow + signal - 2,
        params={"fast": float(fast), "slow": float(slow), "signal": float(signal)},
    )
