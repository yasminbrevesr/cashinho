"""Indicadores base: medias, desvio, ATR, inclinacao, maximas/minimas moveis.

Todas as funcoes recebem listas de float e devolvem listas do mesmo tamanho,
com ``None`` nas posicoes em que o indicador ainda nao tem dados suficientes.
Isso mantem os indices alinhados com a serie de candles.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

Num = Optional[float]


def sma(values: Sequence[float], period: int) -> list[Num]:
    """Media movel simples."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    soma = sum(values[:period])
    out[period - 1] = soma / period
    for i in range(period, len(values)):
        soma += values[i] - values[i - period]
        out[i] = soma / period
    return out


def ema(values: Sequence[float], period: int) -> list[Num]:
    """Media movel exponencial (semente = SMA do primeiro bloco)."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rma(values: Sequence[float], period: int) -> list[Num]:
    """Media suavizada de Wilder (usada em RSI, ATR e ADX)."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def stdev(values: Sequence[float], period: int) -> list[Num]:
    """Desvio padrao movel (populacional, como usam as Bandas de Bollinger)."""
    out: list[Num] = [None] * len(values)
    if period <= 1 or len(values) < period:
        return out
    for i in range(period - 1, len(values)):
        janela = values[i - period + 1 : i + 1]
        m = sum(janela) / period
        var = sum((v - m) ** 2 for v in janela) / period
        out[i] = math.sqrt(var)
    return out


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    """True Range candle a candle."""
    out: list[float] = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[i] - lows[i])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list[Num]:
    """Average True Range (Wilder)."""
    return rma(true_range(highs, lows, closes), period)


def rolling_max(values: Sequence[float], period: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    for i in range(len(values)):
        if i + 1 >= period:
            out[i] = max(values[i - period + 1 : i + 1])
    return out


def rolling_min(values: Sequence[float], period: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    for i in range(len(values)):
        if i + 1 >= period:
            out[i] = min(values[i - period + 1 : i + 1])
    return out


def roc(values: Sequence[float], period: int) -> list[Num]:
    """Rate of change em % (variacao percentual em N candles)."""
    out: list[Num] = [None] * len(values)
    for i in range(period, len(values)):
        base = values[i - period]
        if base:
            out[i] = (values[i] / base - 1.0) * 100.0
    return out


def slope(values: Sequence[Num], period: int) -> Optional[float]:
    """Inclinacao (regressao linear) dos ultimos ``period`` pontos validos.

    Devolve a inclinacao em unidades de preco por candle.
    """
    pontos = [v for v in values[-period:] if v is not None]
    n = len(pontos)
    if n < 3:
        return None
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(pontos) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, pontos))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def slope_pct(values: Sequence[Num], period: int, referencia: Optional[float] = None) -> Optional[float]:
    """Inclinacao normalizada em % do preco por candle (comparavel entre ativos)."""
    s = slope(values, period)
    if s is None:
        return None
    ref = referencia
    if ref is None:
        validos = [v for v in values if v is not None]
        ref = validos[-1] if validos else None
    if not ref:
        return None
    return s / ref * 100.0


def cruzou_para_cima(a: Sequence[Num], b: Sequence[Num]) -> bool:
    """True se a serie ``a`` cruzou ``b`` de baixo para cima no ultimo candle."""
    if len(a) < 2 or len(b) < 2:
        return False
    a0, a1, b0, b1 = a[-2], a[-1], b[-2], b[-1]
    if None in (a0, a1, b0, b1):
        return False
    return a0 <= b0 and a1 > b1


def cruzou_para_baixo(a: Sequence[Num], b: Sequence[Num]) -> bool:
    """True se a serie ``a`` cruzou ``b`` de cima para baixo no ultimo candle."""
    if len(a) < 2 or len(b) < 2:
        return False
    a0, a1, b0, b1 = a[-2], a[-1], b[-2], b[-1]
    if None in (a0, a1, b0, b1):
        return False
    return a0 >= b0 and a1 < b1


def clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def escala(valor: float, neutro: float, saturacao: float) -> float:
    """Converte uma leitura bruta em score -1..+1.

    ``neutro`` e' o valor que gera score 0 e ``saturacao`` o que gera |score| 1.
    """
    if saturacao == neutro:
        return 0.0
    return clamp((valor - neutro) / (saturacao - neutro))
