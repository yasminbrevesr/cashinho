"""Fabricas de candles para os testes de multi-timeframe."""

from __future__ import annotations

from datetime import datetime, timedelta

from cashinho.models import BRT, Candle, Series

DIA = (2026, 8, 20)  # quinta-feira


def ts(hora: int, minuto: int = 0, segundo: int = 0, dia: int = DIA[2]) -> datetime:
    return datetime(DIA[0], DIA[1], dia, hora, minuto, segundo, tzinfo=BRT)


def candle(inicio: datetime, o: float, h: float, l: float, c: float, v: float = 1_000.0) -> Candle:
    return Candle(inicio, o, h, l, c, v)


def serie_1m(
    symbol: str = "PETR4",
    inicio: datetime | None = None,
    n: int = 38,
    preco0: float = 30.0,
    passo: float = 0.01,
) -> Series:
    """Serie de 1m comecando na abertura (10:00), um candle por minuto."""
    inicio = inicio or ts(10, 0)
    candles = []
    preco = preco0
    for i in range(n):
        abertura = preco
        fechamento = preco + passo
        candles.append(
            candle(
                inicio + timedelta(minutes=i),
                abertura,
                max(abertura, fechamento) + 0.02,
                min(abertura, fechamento) - 0.02,
                fechamento,
                1_000.0 + i,
            )
        )
        preco = fechamento
    return Series(symbol, "1m", candles)


def serie_1m_sessao(dia: int = DIA[2], hora_inicial: int = 10, minutos: int = 475, symbol: str = "PETR4") -> Series:
    """Sessao inteira em candles de 1m (10:00 as 17:55 = 475 minutos)."""
    return serie_1m(symbol=symbol, inicio=ts(hora_inicial, 0, dia=dia), n=minutos)


def concatena(*series: Series) -> Series:
    candles = [c for s in series for c in s.candles]
    candles.sort(key=lambda c: c.ts)
    return Series(series[0].symbol, series[0].timeframe, candles)


def serie_tf(timeframe: str, n: int, minutos_por_candle: int, inicio: datetime | None = None,
             symbol: str = "PETR4") -> Series:
    """Serie ja pronta em um timeframe qualquer (sem passar por resample)."""
    inicio = inicio or ts(10, 0)
    candles = []
    preco = 30.0
    for i in range(n):
        abertura = preco
        fechamento = preco + 0.05
        candles.append(
            candle(
                inicio + timedelta(minutes=minutos_por_candle * i),
                abertura,
                max(abertura, fechamento) + 0.05,
                min(abertura, fechamento) - 0.05,
                fechamento,
                5_000.0,
            )
        )
        preco = fechamento
    return Series(symbol, timeframe, candles)
