"""Indicadores de momento: RSI, MACD, Estocastico e ADX/DI."""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from .core import Num, ema, rma, sma


def rsi(closes: Sequence[float], period: int = 14) -> list[Num]:
    """Indice de Forca Relativa (Wilder)."""
    out: list[Num] = [None] * len(closes)
    if len(closes) <= period:
        return out
    ganhos = [0.0]
    perdas = [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        ganhos.append(max(d, 0.0))
        perdas.append(max(-d, 0.0))
    # a primeira media de Wilder usa os candles 1..period
    avg_g = sum(ganhos[1 : period + 1]) / period
    avg_p = sum(perdas[1 : period + 1]) / period
    def _rsi(g: float, p: float) -> float:
        if p == 0:
            return 100.0
        rs = g / p
        return 100.0 - 100.0 / (1.0 + rs)
    out[period] = _rsi(avg_g, avg_p)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + ganhos[i]) / period
        avg_p = (avg_p * (period - 1) + perdas[i]) / period
        out[i] = _rsi(avg_g, avg_p)
    return out


class MACD(NamedTuple):
    macd: list[Num]
    signal: list[Num]
    hist: list[Num]


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
    """MACD classico (12/26/9)."""
    ef = ema(closes, fast)
    es = ema(closes, slow)
    linha: list[Num] = [
        (a - b) if (a is not None and b is not None) else None for a, b in zip(ef, es)
    ]
    validos = [v for v in linha if v is not None]
    inicio = len(linha) - len(validos)
    sig_validos = ema(validos, signal) if validos else []
    sig: list[Num] = [None] * inicio + list(sig_validos)
    sig += [None] * (len(linha) - len(sig))
    hist: list[Num] = [
        (m - s) if (m is not None and s is not None) else None for m, s in zip(linha, sig)
    ]
    return MACD(linha, sig, hist)


class Stoch(NamedTuple):
    k: list[Num]
    d: list[Num]


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
    suavizacao_k: int = 3,
    suavizacao_d: int = 3,
) -> Stoch:
    """Estocastico lento."""
    bruto: list[Num] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        bruto[i] = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0
    validos = [v for v in bruto if v is not None]
    inicio = len(bruto) - len(validos)
    k_s = sma(validos, suavizacao_k) if validos else []
    k: list[Num] = [None] * inicio + list(k_s)
    k += [None] * (len(bruto) - len(k))
    k_validos = [v for v in k if v is not None]
    inicio_d = len(k) - len(k_validos)
    d_s = sma(k_validos, suavizacao_d) if k_validos else []
    d: list[Num] = [None] * inicio_d + list(d_s)
    d += [None] * (len(k) - len(d))
    return Stoch(k, d)


class ADX(NamedTuple):
    adx: list[Num]
    di_mais: list[Num]
    di_menos: list[Num]


def adx(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> ADX:
    """ADX e DI+/DI- (forca e direcao da tendencia)."""
    n = len(highs)
    vazio: list[Num] = [None] * n
    if n < period * 2 + 1:
        return ADX(vazio, list(vazio), list(vazio))

    tr: list[float] = [0.0]
    dm_mais: list[float] = [0.0]
    dm_menos: list[float] = [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        dm_mais.append(up if (up > down and up > 0) else 0.0)
        dm_menos.append(down if (down > up and down > 0) else 0.0)
        pc = closes[i - 1]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))

    tr_s = rma(tr[1:], period)
    dmp_s = rma(dm_mais[1:], period)
    dmm_s = rma(dm_menos[1:], period)

    dip: list[Num] = [None] * n
    dim: list[Num] = [None] * n
    dx: list[Optional[float]] = [None] * n
    for j in range(len(tr_s)):
        i = j + 1
        t, p, m = tr_s[j], dmp_s[j], dmm_s[j]
        if t is None or p is None or m is None or t == 0:
            continue
        dip[i] = 100.0 * p / t
        dim[i] = 100.0 * m / t
        soma = dip[i] + dim[i]
        dx[i] = 0.0 if soma == 0 else 100.0 * abs(dip[i] - dim[i]) / soma

    dx_validos = [v for v in dx if v is not None]
    inicio = n - len(dx_validos)
    adx_s = rma(dx_validos, period) if dx_validos else []
    saida: list[Num] = [None] * inicio + list(adx_s)
    saida += [None] * (n - len(saida))
    return ADX(saida, dip, dim)
