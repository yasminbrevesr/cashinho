"""Series desenhadas a mao, com pivos inequivocos.

Candle de alta ganha pavio em cima, candle de baixa ganha pavio embaixo. Isso
faz o vertice de cada perna ser, sem empate, a maxima (ou minima) local - os
pivos caem exatamente onde o teste espera.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from cashinho.models import BRT, Candle, Series


def ts(hora: int = 10, minuto: int = 0, dia: int = 20) -> datetime:
    return datetime(2026, 8, dia, hora, minuto, tzinfo=BRT)


def serie_de_closes(
    closes: Sequence[float],
    symbol: str = "PETR4",
    timeframe: str = "5m",
    sombra: float = 0.02,
    volume: float = 10_000.0,
    inicio: datetime | None = None,
    minutos: int = 5,
) -> Series:
    inicio = inicio or ts()
    candles: list[Candle] = []
    anterior = closes[0]
    for i, c in enumerate(closes):
        abertura = anterior
        if c >= abertura:  # candle de alta: pavio so em cima
            high, low = c + sombra, abertura
        else:  # candle de baixa: pavio so embaixo
            high, low = abertura, c - sombra
        candles.append(Candle(inicio + timedelta(minutes=minutos * i), abertura, high, low, c, volume))
        anterior = c
    return Series(symbol, timeframe, candles)


def caminho(pontos: Sequence[float], passos: int = 3) -> tuple[list[float], list[int]]:
    """Caminho linear entre os pontos. Devolve (closes, indices dos vertices)."""
    closes = [float(pontos[0])]
    vertices = [0]
    for destino in pontos[1:]:
        origem = closes[-1]
        for k in range(1, passos + 1):
            closes.append(origem + (destino - origem) * k / passos)
        vertices.append(len(closes) - 1)
    return closes, vertices


def serie_zigzag(pontos: Sequence[float], passos: int = 3, **kwargs) -> tuple[Series, list[int]]:
    closes, vertices = caminho(pontos, passos)
    return serie_de_closes(closes, **kwargs), vertices


def recorta(serie: Series, ate: int) -> Series:
    """Serie truncada - simula o que existia em um instante anterior."""
    return Series(serie.symbol, serie.timeframe, serie.candles[:ate])
