"""Indicadores de volume: VWAP (com bandas), OBV, volume relativo e perfil de volume."""

from __future__ import annotations

import math
from typing import NamedTuple, Optional, Sequence

from ..models import BRT, Candle
from .core import Num, sma


class VWAP(NamedTuple):
    vwap: list[Num]
    banda_sup1: list[Num]
    banda_inf1: list[Num]
    banda_sup2: list[Num]
    banda_inf2: list[Num]


def vwap_sessao(candles: Sequence[Candle], desvios: tuple[float, float] = (1.0, 2.0)) -> VWAP:
    """VWAP acumulado por pregao, reiniciando a cada dia, com bandas de desvio.

    A VWAP e' a referencia de preco justo intradiario mais usada por
    institucionais; as bandas medem o quanto o preco esticou em relacao a ela.
    """
    n = len(candles)
    vw: list[Num] = [None] * n
    s1u: list[Num] = [None] * n
    s1d: list[Num] = [None] * n
    s2u: list[Num] = [None] * n
    s2d: list[Num] = [None] * n

    dia = None
    pv = 0.0
    vol = 0.0
    pv2 = 0.0
    for i, c in enumerate(candles):
        d = c.ts.astimezone(BRT).date()
        if d != dia:
            dia, pv, vol, pv2 = d, 0.0, 0.0, 0.0
        tp = c.typical
        v = c.volume if c.volume > 0 else 1.0
        pv += tp * v
        pv2 += (tp ** 2) * v
        vol += v
        media = pv / vol
        vw[i] = media
        var = max(pv2 / vol - media ** 2, 0.0)
        dp = math.sqrt(var)
        s1u[i] = media + desvios[0] * dp
        s1d[i] = media - desvios[0] * dp
        s2u[i] = media + desvios[1] * dp
        s2d[i] = media - desvios[1] * dp
    return VWAP(vw, s1u, s1d, s2u, s2d)


def vwap_ancorada(candles: Sequence[Candle], indice_ancora: int) -> list[Num]:
    """VWAP ancorada a partir de um candle especifico (topo/fundo relevante)."""
    n = len(candles)
    out: list[Num] = [None] * n
    pv = 0.0
    vol = 0.0
    for i in range(max(indice_ancora, 0), n):
        c = candles[i]
        v = c.volume if c.volume > 0 else 1.0
        pv += c.typical * v
        vol += v
        out[i] = pv / vol
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> list[float]:
    """On Balance Volume: fluxo acumulado de volume conforme o preco fecha."""
    out = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def volume_relativo(volumes: Sequence[float], period: int = 20) -> list[Num]:
    """Volume do candle dividido pela media dos ultimos N candles (1.0 = normal)."""
    m = sma(volumes, period)
    out: list[Num] = [None] * len(volumes)
    for i, med in enumerate(m):
        if med:
            out[i] = volumes[i] / med
    return out


class PerfilVolume(NamedTuple):
    poc: float  # preco de maior volume negociado
    vah: float  # topo da area de valor (70%)
    val: float  # fundo da area de valor (70%)
    bins: list[tuple[float, float, float]]  # (low, high, volume)


def perfil_volume(candles: Sequence[Candle], n_bins: int = 24, area_valor: float = 0.70) -> Optional[PerfilVolume]:
    """Perfil de volume simplificado (volume distribuido no range de cada candle).

    Devolve POC (preco de controle) e a area de valor, otimos como suporte /
    resistencia porque marcam onde o mercado realmente negociou.
    """
    if not candles:
        return None
    lo = min(c.low for c in candles)
    hi = max(c.high for c in candles)
    if hi <= lo:
        return None
    largura = (hi - lo) / n_bins
    baldes = [0.0] * n_bins
    for c in candles:
        v = c.volume if c.volume > 0 else 1.0
        # os dois indices precisam do mesmo limite: um candle parado na
        # maxima da serie cai um balde alem do fim e deixava n = 0
        i0 = min(max(int((c.low - lo) / largura), 0), n_bins - 1)
        i1 = min(max(int((c.high - lo) / largura), 0), n_bins - 1)
        n = i1 - i0 + 1
        parte = v / n
        for i in range(i0, i1 + 1):
            baldes[i] += parte

    total = sum(baldes)
    if total <= 0:
        return None
    poc_i = max(range(n_bins), key=lambda i: baldes[i])
    incluidos = {poc_i}
    acumulado = baldes[poc_i]
    baixo, alto = poc_i - 1, poc_i + 1
    while acumulado < total * area_valor and (baixo >= 0 or alto < n_bins):
        vb = baldes[baixo] if baixo >= 0 else -1.0
        va = baldes[alto] if alto < n_bins else -1.0
        if va >= vb:
            incluidos.add(alto)
            acumulado += va
            alto += 1
        else:
            incluidos.add(baixo)
            acumulado += vb
            baixo -= 1
    val = lo + min(incluidos) * largura
    vah = lo + (max(incluidos) + 1) * largura
    poc = lo + (poc_i + 0.5) * largura
    bins = [(lo + i * largura, lo + (i + 1) * largura, baldes[i]) for i in range(n_bins)]
    return PerfilVolume(poc=poc, vah=vah, val=val, bins=bins)


def fluxo_direcional(candles: Sequence[Candle], period: int = 20) -> Optional[float]:
    """Proporcao do volume recente em candles de alta (0..1).

    Acima de 0,6 indica pressao compradora; abaixo de 0,4, pressao vendedora.
    """
    janela = candles[-period:]
    if not janela:
        return None
    total = sum((c.volume if c.volume > 0 else 1.0) for c in janela)
    if total <= 0:
        return None
    alta = sum((c.volume if c.volume > 0 else 1.0) for c in janela if c.close > c.open)
    neutro = sum((c.volume if c.volume > 0 else 1.0) for c in janela if c.close == c.open)
    return (alta + neutro * 0.5) / total
