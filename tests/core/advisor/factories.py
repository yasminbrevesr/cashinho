"""Series com comportamento controlado para os testes do Advisor."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.advisor import Estatistica, RecomendacaoAtual
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)   # quinta-feira


def serie_1m(minutos: int = 400, base: float = 30.0, symbol: str = "PETR4",
             inicio: Optional[datetime] = None, forma=None,
             volume: float = 10_000.0) -> Series:
    """Serie de 1m com a forma que o teste pedir.

    ``forma(i)`` devolve o preco do minuto ``i``. O padrao e' uma alta suave.
    """
    comeco = inicio or ABERTURA
    forma = forma or (lambda i: base * (1 + 0.0004 * i))
    candles = []
    for i in range(minutos):
        abertura = forma(i)
        fechamento = forma(i + 1)
        alta = max(abertura, fechamento) * 1.0008
        baixa = min(abertura, fechamento) * 0.9992
        candles.append(Candle(comeco + timedelta(minutes=i), abertura, alta,
                              baixa, fechamento, volume))
    return Series(symbol, "1m", candles)


def tendencia(minutos: int = 400, inclinacao: float = 0.0004) -> Series:
    """Movimento direcional limpo - pouco ruido."""
    return serie_1m(minutos, forma=lambda i: 30.0 * (1 + inclinacao * i))


def onda(minutos: int = 400, amplitude: float = 0.004, periodo: float = 19.0) -> Series:
    """Oscilacao PERIODICA - e isso nao e' ruido, e' ciclo.

    Uma senoide de 19 minutos e' perfeitamente operavel no 1m (cada meia onda
    e' um movimento) e imprestavel no 15m (cada candle come um quarto de
    ciclo). O Advisor acerta ao preferir o timeframe fino aqui - por isso esta
    serie NAO serve para testar aversao a ruido.
    """
    volta = 2 * math.pi / periodo
    return serie_1m(minutos,
                    forma=lambda i: 30.0 * (1 + amplitude * math.sin(i * volta)))


def lateral_ruidosa(minutos: int = 400, amplitude: float = 0.0025,
                    semente: int = 7) -> Series:
    """Ruido de verdade: nao periodico, com reversao a media.

    Deterministico (gerador com semente fixa), para o teste repetir. Aqui o
    preco anda muito e nao chega a lugar nenhum em NENHUMA escala - que e' o
    caso em que a granularidade fina e' a pior de operar.
    """
    x = semente
    passos = []
    nivel = 0.0
    for _ in range(minutos + 2):
        x = (x * 1103515245 + 12345) % 2147483648
        sorteio = (x / 2147483648) - 0.5
        nivel = nivel * 0.55 + sorteio      # reversao a media: nao acumula
        passos.append(nivel)
    return serie_1m(minutos, forma=lambda i: 30.0 * (1 + amplitude * passos[i]))


def estatistica(trades: int = 30, expectancy: float = 0.45,
                profit_factor: Optional[float] = 1.6,
                drawdown: Optional[float] = 4.2) -> Estatistica:
    return Estatistica(trades=trades, expectancy=expectancy,
                       profit_factor=profit_factor, max_drawdown_pct=drawdown)


def atual(timeframe: str = "5m", score: float = 82.0,
          minutos_atras: float = 60.0, agora: Optional[datetime] = None) -> RecomendacaoAtual:
    instante = agora or (ABERTURA + timedelta(minutes=400))
    return RecomendacaoAtual(timeframe, instante - timedelta(minutes=minutos_atras), score)
