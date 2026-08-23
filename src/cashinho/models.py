"""Modelos de dados do Cashinho.

Tudo aqui e' stdlib puro: o nucleo de analise nao depende de pandas/numpy,
para que o robo rode em qualquer maquina com Python 3.9+.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Iterable, Optional, Sequence

# Fuso de Brasilia. Usamos offset fixo (-03:00) porque o Brasil nao tem
# horario de verao desde 2019 e assim evitamos depender do tzdata do sistema.
BRT = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

TICK_ACAO = 0.01  # variacao minima de precos de acoes na B3
LOTE_PADRAO = 100


class Direction(str, Enum):
    """Direcao de uma operacao."""

    LONG = "COMPRA"
    SHORT = "VENDA"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.LONG else -1

    @property
    def oposta(self) -> "Direction":
        return Direction.SHORT if self is Direction.LONG else Direction.LONG


class CandleInvalidoError(ValueError):
    """Candle que nao pode existir - e por isso nao existe."""


# folga para ruido de ponto flutuante: um close 1e-12 acima da maxima veio de
# aritmetica, nao do mercado
_TOLERANCIA = 1e-9


@dataclass(frozen=True)
class Candle:
    """Um candle OHLCV.

    O candle e' o atomo de todo o sistema: ATR, estrutura, stop, tamanho de
    posicao e preco de ordem saem dele. Por isso ele **recusa estado
    impossivel** em vez de propagar numero sem sentido - maxima abaixo da
    minima, fechamento fora do range, preco negativo, volume negativo. Um
    provedor que receba lixo descarta a linha; o que nao pode e' o lixo entrar
    calado e virar tamanho de posicao la na frente.
    """

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        for nome in ("open", "high", "low", "close"):
            valor = getattr(self, nome)
            if valor != valor or valor in (float("inf"), float("-inf")):
                raise CandleInvalidoError(f"{nome} nao e' um numero ({valor!r})")
            if valor <= 0:
                raise CandleInvalidoError(
                    f"{nome} precisa ser maior que zero (recebido {valor})")
        if self.volume != self.volume or self.volume < 0:
            raise CandleInvalidoError(f"volume negativo ou invalido ({self.volume})")

        folga = _TOLERANCIA * max(1.0, abs(self.high))
        if self.high + folga < self.low:
            raise CandleInvalidoError(
                f"maxima {self.high} abaixo da minima {self.low}")
        for nome in ("open", "close"):
            valor = getattr(self, nome)
            if not (self.low - folga <= valor <= self.high + folga):
                raise CandleInvalidoError(
                    f"{nome} {valor} fora do range [{self.low}, {self.high}]")

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def financeiro(self) -> float:
        """Volume financeiro aproximado do candle (R$)."""
        return self.typical * self.volume


@dataclass
class Series:
    """Serie de candles de um ativo em um timeframe."""

    symbol: str
    timeframe: str
    candles: list[Candle] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.candles)

    def __getitem__(self, item):
        return self.candles[item]

    def __iter__(self):
        return iter(self.candles)

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def volumes(self) -> list[float]:
        return [c.volume for c in self.candles]

    @property
    def last(self) -> Candle:
        return self.candles[-1]

    @property
    def price(self) -> float:
        return self.candles[-1].close

    def tail(self, n: int) -> "Series":
        return Series(self.symbol, self.timeframe, self.candles[-n:])

    def sessions(self) -> list[list[Candle]]:
        """Agrupa os candles por dia de pregao (na ordem cronologica)."""
        grupos: list[list[Candle]] = []
        dia_atual = None
        for c in self.candles:
            dia = c.ts.astimezone(BRT).date()
            if dia != dia_atual:
                grupos.append([])
                dia_atual = dia
            grupos[-1].append(c)
        return grupos

    def sessao_atual(self) -> list[Candle]:
        s = self.sessions()
        return s[-1] if s else []


@dataclass
class Zone:
    """Zona de suporte ou resistencia."""

    low: float
    high: float
    kind: str  # "suporte" | "resistencia"
    touches: int = 1
    strength: float = 0.0  # 0..1
    origem: str = ""

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def distance(self, price: float) -> float:
        if self.contains(price):
            return 0.0
        return self.low - price if price < self.low else price - self.high


# ---------------------------------------------------------------------------
# utilidades de preco
# ---------------------------------------------------------------------------


def arredonda_tick(preco: float, tick: float = TICK_ACAO, modo: str = "nearest") -> float:
    """Arredonda um preco para o tick da B3 (R$ 0,01 para acoes)."""
    if tick <= 0:
        return preco
    q = preco / tick
    if modo == "up":
        n = math.ceil(q - 1e-9)
    elif modo == "down":
        n = math.floor(q + 1e-9)
    else:
        n = math.floor(q + 0.5)
    return round(n * tick, 10)


def formata_preco(preco: Optional[float]) -> str:
    if preco is None:
        return "-"
    return f"{preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formata_dinheiro(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return "R$ " + formata_preco(v)


def media(vals: Iterable[float]) -> float:
    vals = list(vals)
    return sum(vals) / len(vals) if vals else 0.0


def dentro_do_pregao(ts: datetime, abertura: time = time(10, 0), fechamento: time = time(17, 55)) -> bool:
    t = ts.astimezone(BRT)
    if t.weekday() >= 5:
        return False
    return abertura <= t.time() <= fechamento


def ultimo_valor(seq: Sequence[Optional[float]], offset: int = 0) -> Optional[float]:
    """Ultimo valor nao-nulo de uma serie de indicador (offset=1 -> penultimo)."""
    idx = len(seq) - 1 - offset
    if idx < 0:
        return None
    return seq[idx]
