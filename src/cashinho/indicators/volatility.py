"""Volatilidade: Bandas de Bollinger, Keltner, squeeze e ATR percentual."""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from .core import Num, atr, ema, sma, stdev


class Bollinger(NamedTuple):
    superior: list[Num]
    media: list[Num]
    inferior: list[Num]
    largura: list[Num]  # (sup - inf) / media, em %
    percent_b: list[Num]  # posicao do preco dentro das bandas (0..1)


def bollinger(closes: Sequence[float], period: int = 20, mult: float = 2.0) -> Bollinger:
    m = sma(closes, period)
    dp = stdev(closes, period)
    n = len(closes)
    sup: list[Num] = [None] * n
    inf: list[Num] = [None] * n
    larg: list[Num] = [None] * n
    pb: list[Num] = [None] * n
    for i in range(n):
        if m[i] is None or dp[i] is None:
            continue
        sup[i] = m[i] + mult * dp[i]
        inf[i] = m[i] - mult * dp[i]
        if m[i]:
            larg[i] = (sup[i] - inf[i]) / m[i] * 100.0
        if sup[i] != inf[i]:
            pb[i] = (closes[i] - inf[i]) / (sup[i] - inf[i])
    return Bollinger(sup, m, inf, larg, pb)


class Keltner(NamedTuple):
    superior: list[Num]
    media: list[Num]
    inferior: list[Num]


def keltner(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
    mult: float = 1.5,
) -> Keltner:
    m = ema(closes, period)
    a = atr(highs, lows, closes, period)
    n = len(closes)
    sup: list[Num] = [None] * n
    inf: list[Num] = [None] * n
    for i in range(n):
        if m[i] is None or a[i] is None:
            continue
        sup[i] = m[i] + mult * a[i]
        inf[i] = m[i] - mult * a[i]
    return Keltner(sup, m, inf)


def squeeze(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
) -> list[bool]:
    """Squeeze de Bollinger dentro de Keltner: compressao que antecede explosao."""
    bb = bollinger(closes, period)
    kc = keltner(highs, lows, closes, period)
    out = []
    for i in range(len(closes)):
        if None in (bb.superior[i], bb.inferior[i], kc.superior[i], kc.inferior[i]):
            out.append(False)
        else:
            out.append(bb.superior[i] < kc.superior[i] and bb.inferior[i] > kc.inferior[i])
    return out


def atr_percentual(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> list[Num]:
    """ATR em % do preco: permite comparar a volatilidade entre ativos diferentes."""
    a = atr(highs, lows, closes, period)
    out: list[Num] = [None] * len(closes)
    for i, v in enumerate(a):
        if v is not None and closes[i]:
            out[i] = v / closes[i] * 100.0
    return out


def compressao_relativa(largura_bb: Sequence[Num], janela: int = 60) -> Optional[float]:
    """Percentil (0..1) da largura atual das bandas nos ultimos N candles.

    Valores baixos (< 0,25) indicam mercado comprimido - risco de rompimento.
    """
    validos = [v for v in largura_bb[-janela:] if v is not None]
    if len(validos) < 10:
        return None
    atual = validos[-1]
    menores = sum(1 for v in validos if v <= atual)
    return menores / len(validos)
