"""Padroes de candlestick relevantes para day trade.

Cada detector devolve ``Padrao`` com direcao e forca 0..1. Os padroes so sao
usados como confirmacao - nunca como gatilho isolado.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from ..models import Candle, Direction


class Padrao(NamedTuple):
    nome: str
    direcao: Direction
    forca: float  # 0..1
    indice: int


def _corpo_medio(candles: Sequence[Candle], n: int = 20) -> float:
    janela = candles[-n:]
    if not janela:
        return 0.0
    return sum(c.body for c in janela) / len(janela)


def _range_medio(candles: Sequence[Candle], n: int = 20) -> float:
    janela = candles[-n:]
    if not janela:
        return 0.0
    return sum(c.range for c in janela) / len(janela)


def detecta(candles: Sequence[Candle], janela: int = 3) -> list[Padrao]:
    """Detecta padroes nos ultimos ``janela`` candles fechados."""
    achados: list[Padrao] = []
    n = len(candles)
    if n < 5:
        return achados
    corpo_med = _corpo_medio(candles) or 1e-9
    range_med = _range_medio(candles) or 1e-9

    for i in range(max(n - janela, 2), n):
        c = candles[i]
        a = candles[i - 1]
        aa = candles[i - 2]
        rng = c.range or 1e-9

        # --- martelo / estrela cadente (pin bar) ---
        corpo_ref = max(c.body, rng * 0.06)
        if c.lower_shadow >= 2 * corpo_ref and c.upper_shadow <= 0.35 * rng:
            forca = min(1.0, 0.5 + (c.lower_shadow / rng) * 0.5)
            achados.append(Padrao("martelo (pin bar de fundo)", Direction.LONG, round(forca, 2), i))
        if c.upper_shadow >= 2 * corpo_ref and c.lower_shadow <= 0.35 * rng:
            forca = min(1.0, 0.5 + (c.upper_shadow / rng) * 0.5)
            achados.append(Padrao("estrela cadente (pin bar de topo)", Direction.SHORT, round(forca, 2), i))

        # --- engolfo ---
        if c.bullish and a.bearish and c.close >= a.open and c.open <= a.close and c.body > a.body:
            achados.append(Padrao("engolfo de alta", Direction.LONG, round(min(1.0, 0.55 + c.body / (corpo_med * 3)), 2), i))
        if c.bearish and a.bullish and c.close <= a.open and c.open >= a.close and c.body > a.body:
            achados.append(Padrao("engolfo de baixa", Direction.SHORT, round(min(1.0, 0.55 + c.body / (corpo_med * 3)), 2), i))

        # --- marubozu (forca direcional) ---
        if c.body >= 0.82 * rng and c.body > corpo_med * 1.2:
            d = Direction.LONG if c.bullish else Direction.SHORT
            achados.append(Padrao("marubozu", d, 0.6, i))

        # --- inside bar (compressao antes de rompimento) ---
        if c.high <= a.high and c.low >= a.low and a.range > range_med:
            d = Direction.LONG if a.bullish else Direction.SHORT
            achados.append(Padrao("inside bar", d, 0.4, i))

        # --- doji / indecisao (so quando nao ha sombra dominante) ---
        pin = c.lower_shadow >= 2 * corpo_ref or c.upper_shadow >= 2 * corpo_ref
        if c.body <= 0.1 * rng and rng > range_med * 0.6 and not pin:
            achados.append(Padrao("doji (indecisao)", Direction.LONG if a.bearish else Direction.SHORT, 0.25, i))

        # --- estrela da manha / da noite ---
        if aa.bearish and a.body < corpo_med * 0.6 and c.bullish and c.close > (aa.open + aa.close) / 2:
            achados.append(Padrao("estrela da manha", Direction.LONG, 0.75, i))
        if aa.bullish and a.body < corpo_med * 0.6 and c.bearish and c.close < (aa.open + aa.close) / 2:
            achados.append(Padrao("estrela da noite", Direction.SHORT, 0.75, i))

        # --- pinca (tweezer) ---
        tol = range_med * 0.1
        if abs(c.low - a.low) <= tol and c.bullish and a.bearish:
            achados.append(Padrao("pinca de fundo", Direction.LONG, 0.5, i))
        if abs(c.high - a.high) <= tol and c.bearish and a.bullish:
            achados.append(Padrao("pinca de topo", Direction.SHORT, 0.5, i))

    return achados


def vies(padroes: Sequence[Padrao], n_ultimos: int, decaimento: float = 0.6) -> float:
    """Consolida os padroes em um unico score -1..+1, dando mais peso aos recentes."""
    if not padroes:
        return 0.0
    total = 0.0
    peso_total = 0.0
    for p in padroes:
        idade = max(n_ultimos - 1 - p.indice, 0)
        peso = decaimento ** idade
        total += p.direcao.sign * p.forca * peso
        peso_total += peso
    if peso_total == 0:
        return 0.0
    return max(-1.0, min(1.0, total / max(peso_total, 1.0)))


def descreve(padroes: Sequence[Padrao]) -> str:
    if not padroes:
        return "sem padrao relevante"
    nomes = []
    for p in sorted(padroes, key=lambda x: -x.indice)[:3]:
        nomes.append(f"{p.nome} ({'alta' if p.direcao is Direction.LONG else 'baixa'})")
    return ", ".join(nomes)
