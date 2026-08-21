"""Bandas de Bollinger."""

from __future__ import annotations

import pandas as pd

from cashinho.core.indicators.base import IndicatorResult, prepare, validate_period
from cashinho.domain.market import CandleSeries

DEFAULT_PERIOD = 20
DEFAULT_DEVIATIONS = 2.0


def bollinger(
    series: CandleSeries,
    period: int = DEFAULT_PERIOD,
    *,
    deviations: float = DEFAULT_DEVIATIONS,
    column: str = "close",
    ddof: int = 0,
) -> IndicatorResult:
    """Banda central, superior e inferior, mais largura e %B.

    `ddof=0` (desvio populacional) e o padrao das plataformas de grafico.
    O pandas usa `ddof=1` por padrao, o que produziria bandas levemente
    mais largas que as exibidas na corretora. O parametro fica exposto,
    mas o default segue a convencao de mercado.

    `bandwidth` e `percent_b` sao derivados uteis para confluencia:
    largura mede compressao, %B mede posicao relativa do preco. Nenhum
    dos dois e um sinal.
    """
    validate_period(period, minimum=2)
    if deviations <= 0:
        raise ValueError(f"deviations deve ser positivo; recebido {deviations}")

    frame = prepare(series, minimum=period, indicator=f"BB({period},{deviations})")
    prices = frame[column]

    middle = prices.rolling(window=period, min_periods=period).mean()
    std = prices.rolling(window=period, min_periods=period).std(ddof=ddof)
    upper = middle + deviations * std
    lower = middle - deviations * std
    width = upper - lower

    return IndicatorResult(
        name=f"BB({period},{deviations:g})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame(
            {
                "middle": middle,
                "upper": upper,
                "lower": lower,
                "bandwidth": (width / middle).where(middle != 0),
                "percent_b": ((prices - lower) / width).where(width != 0),
            }
        ),
        warmup=period - 1,
        params={"period": float(period), "deviations": float(deviations)},
    )
