"""Valores de referencia dos indicadores (golden test).

Proposito: travar o comportamento numerico. Qualquer mudanca futura na
suavizacao, na semente ou na ordem das operacoes quebra estes testes, e
a quebra e o alerta.

RESSALVA SOBRE A REFERENCIA
---------------------------
A serie de 20 fechamentos abaixo e o exemplo classico usado na
literatura de analise tecnica para demonstrar o RSI de Wilder. Os
valores esperados foram produzidos pela propria implementacao do
Cashinho apos conferencia manual da formula, e coincidem com os valores
comumente publicados para esse conjunto.

Isso e uma trava de regressao, nao uma validacao contra fonte
autoritativa. Uma validacao de verdade exige comparar com dados de
referencia de terceiro — recomendado antes de qualquer estrategia
depender destes numeros para decidir entrada ou stop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from statistics import pstdev

import pytest

from cashinho.core.indicators import atr, bollinger, ema, macd, rsi, sma, vwap
from cashinho.domain.enums import Timeframe
from cashinho.domain.market import Candle, CandleSeries

WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
]

BASE = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


def _series(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[int] | None = None,
) -> CandleSeries:
    candles = []
    for i, close in enumerate(closes):
        open_time = BASE + Timeframe.M5.duration * i
        price = Decimal(str(close))
        high = Decimal(str(highs[i])) if highs else price
        low = Decimal(str(lows[i])) if lows else price
        candles.append(
            Candle(
                open_time=open_time,
                close_time=open_time + Timeframe.M5.duration,
                open=price,
                high=max(high, price),
                low=min(low, price),
                close=price,
                volume=volumes[i] if volumes else 1000,
            )
        )
    return CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=tuple(candles),
        source="golden",
        fetched_at=BASE,
    )


def test_rsi_serie_de_referencia() -> None:
    valores = rsi(_series(WILDER_CLOSES), 14).values["rsi_14"]
    assert valores.iloc[14] == pytest.approx(70.46, abs=0.01)
    assert valores.iloc[15] == pytest.approx(66.25, abs=0.01)
    assert valores.iloc[19] == pytest.approx(57.92, abs=0.01)


def test_sma_serie_de_referencia() -> None:
    valores = sma(_series(WILDER_CLOSES), 14).values["sma_14"]
    esperado = sum(WILDER_CLOSES[:14]) / 14
    assert valores.iloc[13] == pytest.approx(esperado, abs=1e-9)


def test_ema_serie_de_referencia() -> None:
    """Primeiro valor = SMA dos 14 primeiros; o seguinte segue a recursao."""
    valores = ema(_series(WILDER_CLOSES), 14).values["ema_14"]
    semente = sum(WILDER_CLOSES[:14]) / 14
    alpha = 2 / 15
    assert valores.iloc[13] == pytest.approx(semente, abs=1e-9)
    assert valores.iloc[14] == pytest.approx(
        WILDER_CLOSES[14] * alpha + semente * (1 - alpha), abs=1e-9
    )


def test_atr_serie_de_referencia() -> None:
    highs = [c + 0.30 for c in WILDER_CLOSES]
    lows = [c - 0.30 for c in WILDER_CLOSES]
    valores = atr(_series(WILDER_CLOSES, highs=highs, lows=lows), 14).values["atr_14"]
    assert valores.iloc[:14].isna().all()
    assert valores.iloc[14] == pytest.approx(0.7064, abs=0.001)


def test_macd_serie_de_referencia() -> None:
    """Serie linear tem resultado analitico fechado.

    Para inclinacao `s`, a EMA(n) de uma reta fica atrasada em
    `s * (n - 1) / 2`. Logo o MACD converge para
    `s * ((slow - 1) / 2 - (fast - 1) / 2)` = 0.25 * (12.5 - 5.5) = 1.75.
    Verificacao independente da implementacao, e nao valor copiado dela.
    """
    slope = 0.25
    closes = [40 + i * slope for i in range(60)]
    esperado = slope * ((26 - 1) / 2 - (12 - 1) / 2)
    ultimo = macd(_series(closes)).last()
    assert ultimo["macd"] == pytest.approx(esperado, abs=0.001)
    assert ultimo["signal"] == pytest.approx(esperado, abs=0.001)
    assert ultimo["histogram"] == pytest.approx(
        ultimo["macd"] - ultimo["signal"], abs=1e-9
    )


def test_bollinger_serie_de_referencia() -> None:
    """Conferido contra `statistics.pstdev`, independente do pandas."""
    ultimos = WILDER_CLOSES[-14:]
    media = sum(ultimos) / 14
    desvio = pstdev(ultimos)
    ultimo = bollinger(_series(WILDER_CLOSES), 14).last()
    assert ultimo["middle"] == pytest.approx(media, abs=1e-9)
    assert ultimo["upper"] == pytest.approx(media + 2 * desvio, abs=1e-9)
    assert ultimo["lower"] == pytest.approx(media - 2 * desvio, abs=1e-9)
    assert ultimo["middle"] == pytest.approx(45.9164, abs=0.001)


def test_vwap_serie_de_referencia() -> None:
    volumes = [1000 + i * 100 for i in range(20)]
    ultimo = vwap(_series(WILDER_CLOSES, volumes=volumes)).last()
    notional = sum(c * v for c, v in zip(WILDER_CLOSES, volumes, strict=True))
    assert ultimo["vwap"] == pytest.approx(notional / sum(volumes), abs=1e-6)
    assert ultimo["session_volume"] == pytest.approx(sum(volumes))
