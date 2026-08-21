"""VWAP — preco medio ponderado por volume.

PONTO CRITICO: ANCORAGEM
------------------------
VWAP e um acumulado, nao uma janela movel. Sem reinicio a cada pregao, o
acumulado do dia 1 continua influenciando o dia 20 e o indicador vira uma
media de longo prazo disfarcada, com valor cada vez mais distante do
preco e sem nenhum uso operacional.

Por isso a ancoragem e obrigatoria e explicita, e o corte de sessao usa o
fuso da B3 — nao UTC. Ancorar na virada do dia UTC (21:00 em Brasilia)
cortaria o pregao no meio do after-market e produziria dois VWAPs
parciais por dia.
"""

from __future__ import annotations

from enum import StrEnum

import pandas as pd

from cashinho.core.indicators.base import IndicatorResult, prepare
from cashinho.core.time.b3_calendar import B3_TIMEZONE
from cashinho.domain.market import CandleSeries

MINIMUM_CANDLES = 2


class VwapAnchor(StrEnum):
    """Ponto de reinicio do acumulado."""

    SESSION = "SESSION"
    """Reinicia a cada pregao. Padrao para Day Trade."""

    FULL = "FULL"
    """Acumula toda a serie. Uso restrito a janelas ja recortadas a mao
    (VWAP ancorado em um evento especifico, por exemplo)."""


def typical_price(frame: pd.DataFrame) -> pd.Series:
    """Preco tipico: (high + low + close) / 3.

    Usar apenas o fechamento ignoraria onde os negocios de fato
    ocorreram dentro do candle.
    """
    return (frame["high"] + frame["low"] + frame["close"]) / 3.0


def vwap(
    series: CandleSeries,
    *,
    anchor: VwapAnchor = VwapAnchor.SESSION,
    timezone: str = str(B3_TIMEZONE),
) -> IndicatorResult:
    """VWAP acumulado, reiniciado conforme a ancora.

    Devolve tambem `session_volume` para que o consumidor saiba quanto
    volume sustenta o valor: VWAP dos primeiros minutos de pregao apoia-se
    em pouquissimos negocios e nao merece o mesmo peso do VWAP das 16h.

    Candles com volume zero nao deslocam o acumulado, mas tambem nao
    invalidam a serie — apenas nao contribuem.
    """
    frame = prepare(series, minimum=MINIMUM_CANDLES, indicator="VWAP", intraday_only=True)

    price = typical_price(frame)
    volume = frame["volume"].astype("float64")
    notional = price * volume

    if anchor is VwapAnchor.SESSION:
        index = pd.DatetimeIndex(frame.index)
        sessions = index.tz_convert(timezone).date
        grouped_notional = notional.groupby(sessions).cumsum()
        grouped_volume = volume.groupby(sessions).cumsum()
    else:
        grouped_notional = notional.cumsum()
        grouped_volume = volume.cumsum()

    values = (grouped_notional / grouped_volume.where(grouped_volume > 0)).astype("float64")

    return IndicatorResult(
        name=f"VWAP({anchor.value})",
        symbol=series.symbol,
        timeframe=series.timeframe,
        values=pd.DataFrame(
            {
                "vwap": values,
                "typical_price": price,
                "session_volume": grouped_volume,
            }
        ),
        warmup=0,
        params={"anchor_session": 1.0 if anchor is VwapAnchor.SESSION else 0.0},
    )
