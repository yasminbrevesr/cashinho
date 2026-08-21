"""Series deterministicas (sem random) para os testes de estrategia."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.models import BRT, Candle, Series

INICIO = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)


def serie_de_closes(
    closes: Sequence[float],
    volumes: Optional[Sequence[float]] = None,
    pavio: float = 0.002,
    symbol: str = "PETR4",
    timeframe: str = "5m",
) -> Series:
    """Candles a partir de uma lista de fechamentos.

    ``pavio`` controla o tamanho das sombras - e' o que define o ATR da serie
    nos testes de faixa de volatilidade.
    """
    candles: list[Candle] = []
    anterior = closes[0]
    for i, fechamento in enumerate(closes):
        abertura = anterior
        topo = max(abertura, fechamento)
        base = min(abertura, fechamento)
        candles.append(
            Candle(
                ts=INICIO + timedelta(minutes=5 * i),
                open=abertura,
                high=topo * (1 + pavio),
                low=base * (1 - pavio),
                close=fechamento,
                volume=(volumes[i] if volumes else 10_000.0),
            )
        )
        anterior = fechamento
    return Series(symbol, timeframe, candles)


def _volumes(n: int, ultimo: float = 1.0) -> list[float]:
    """Volume constante, com um multiplicador so no ultimo candle."""
    vols = [10_000.0] * n
    vols[-1] = 10_000.0 * ultimo
    return vols


def serie_alta(n: int = 90, passo: float = 0.001, volume_final: float = 2.0, pavio: float = 0.002) -> Series:
    closes = [30.0 * (1 + passo) ** i for i in range(n)]
    return serie_de_closes(closes, _volumes(n, volume_final), pavio)


def serie_baixa(n: int = 90, passo: float = 0.001, volume_final: float = 2.0, pavio: float = 0.002) -> Series:
    closes = [30.0 * (1 - passo) ** i for i in range(n)]
    return serie_de_closes(closes, _volumes(n, volume_final), pavio)


def serie_embaralhada(subida: int = 80, queda: int = 7) -> Series:
    """Alta seguida de uma queda que desfaz o empilhamento.

    No ultimo candle a EMA9 ja caiu abaixo da EMA21 mas segue acima da EMA50:
    as medias ficam fora de ordem nos dois sentidos, que e' exatamente o caso
    em que a estrategia nao deve enxergar vies nenhum.
    """
    closes = [30.0 * 1.001 ** i for i in range(subida)]
    for _ in range(queda):
        closes.append(closes[-1] * 0.996)
    return serie_de_closes(closes, _volumes(len(closes), 2.0))


def serie_parada(n: int = 90) -> Series:
    """Preco cravado e pavio minusculo: ATR abaixo do minimo operavel."""
    return serie_de_closes([30.0] * n, _volumes(n, 2.0), pavio=0.0002)


def serie_explosiva(n: int = 90, passo: float = 0.001) -> Series:
    """Mesma tendencia, mas com pavios enormes: ATR acima do maximo."""
    closes = [30.0 * (1 + passo) ** i for i in range(n)]
    return serie_de_closes(closes, _volumes(n, 2.0), pavio=0.025)
