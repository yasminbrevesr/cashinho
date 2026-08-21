"""Estrutura de mercado: pivos, suportes/resistencias, tendencia, Fibonacci e range de abertura."""

from __future__ import annotations

from datetime import time
from typing import NamedTuple, Optional, Sequence

from ..models import BRT, Candle, Direction, Zone
from .core import Num, ema, slope_pct
from .momentum import adx


class Pivo(NamedTuple):
    indice: int
    preco: float
    tipo: str  # "topo" | "fundo"


def pivos(candles: Sequence[Candle], esquerda: int = 3, direita: int = 3) -> list[Pivo]:
    """Encontra topos e fundos (fractais) confirmados por N candles de cada lado."""
    out: list[Pivo] = []
    n = len(candles)
    for i in range(esquerda, n - direita):
        h = candles[i].high
        l = candles[i].low
        eh_topo = all(candles[j].high <= h for j in range(i - esquerda, i)) and all(
            candles[j].high < h for j in range(i + 1, i + direita + 1)
        )
        eh_fundo = all(candles[j].low >= l for j in range(i - esquerda, i)) and all(
            candles[j].low > l for j in range(i + 1, i + direita + 1)
        )
        if eh_topo:
            out.append(Pivo(i, h, "topo"))
        if eh_fundo:
            out.append(Pivo(i, l, "fundo"))
    return out


def zonas_suporte_resistencia(
    candles: Sequence[Candle],
    preco_ref: float,
    tolerancia_pct: float = 0.25,
    esquerda: int = 3,
    direita: int = 3,
    origem: str = "intraday",
) -> list[Zone]:
    """Agrupa pivos proximos em zonas de suporte/resistencia com forca 0..1.

    A forca considera numero de toques, quao recente e' a zona e o volume
    negociado nos candles que a formaram.
    """
    ps = pivos(candles, esquerda, direita)
    if not ps:
        return []
    tol = preco_ref * tolerancia_pct / 100.0
    n = len(candles)
    vol_medio = sum(c.volume for c in candles) / n if n else 1.0

    clusters: list[dict] = []
    for p in sorted(ps, key=lambda x: x.preco):
        if clusters and abs(p.preco - clusters[-1]["media"]) <= tol:
            c = clusters[-1]
            c["precos"].append(p.preco)
            c["indices"].append(p.indice)
            c["media"] = sum(c["precos"]) / len(c["precos"])
        else:
            clusters.append({"precos": [p.preco], "indices": [p.indice], "media": p.preco})

    zonas: list[Zone] = []
    for c in clusters:
        low, high = min(c["precos"]), max(c["precos"])
        if high - low < tol / 2:
            meio = (high + low) / 2
            low, high = meio - tol / 2, meio + tol / 2
        toques = len(c["precos"])
        recencia = max(c["indices"]) / max(n - 1, 1)
        vols = [candles[i].volume for i in c["indices"]]
        peso_vol = (sum(vols) / len(vols)) / vol_medio if vol_medio else 1.0
        forca = min(
            1.0,
            0.32 * min(toques / 3.0, 1.0)
            + 0.30 * recencia
            + 0.18 * min(peso_vol / 2.0, 1.0)
            + 0.20,
        )
        meio = (low + high) / 2
        kind = "resistencia" if meio > preco_ref else "suporte"
        zonas.append(Zone(low=low, high=high, kind=kind, touches=toques, strength=forca, origem=origem))
    return zonas


def mescla_zonas(zonas: Sequence[Zone], preco_ref: float, tolerancia_pct: float = 0.25) -> list[Zone]:
    """Funde zonas de origens diferentes que se sobrepoem, somando forca (confluencia)."""
    if not zonas:
        return []
    tol = preco_ref * tolerancia_pct / 100.0
    ordenadas = sorted(zonas, key=lambda z: z.mid)
    saida: list[Zone] = []
    for z in ordenadas:
        if saida and z.low - saida[-1].high <= tol:
            a = saida[-1]
            nova = Zone(
                low=min(a.low, z.low),
                high=max(a.high, z.high),
                kind=a.kind,
                touches=a.touches + z.touches,
                strength=min(1.0, a.strength + z.strength * 0.45),
                origem=f"{a.origem}+{z.origem}" if z.origem not in a.origem else a.origem,
            )
            saida[-1] = nova
        else:
            saida.append(z)
    for i, z in enumerate(saida):
        saida[i] = Zone(z.low, z.high, "resistencia" if z.mid > preco_ref else "suporte",
                        z.touches, z.strength, z.origem)
    return saida


def resistencias_acima(zonas: Sequence[Zone], preco: float) -> list[Zone]:
    return sorted([z for z in zonas if z.low > preco], key=lambda z: z.low)


def suportes_abaixo(zonas: Sequence[Zone], preco: float) -> list[Zone]:
    return sorted([z for z in zonas if z.high < preco], key=lambda z: -z.high)


class Tendencia(NamedTuple):
    direcao: Optional[Direction]
    forca: float  # 0..1
    descricao: str
    adx: Optional[float]
    inclinacao_pct: Optional[float]
    estrutura: str  # "alta" | "baixa" | "lateral"


def classifica_tendencia(candles: Sequence[Candle], curta: int = 9, media: int = 21, longa: int = 50) -> Tendencia:
    """Classifica a tendencia cruzando empilhamento de medias, ADX e estrutura de pivos."""
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    if len(closes) < longa + 5:
        return Tendencia(None, 0.0, "dados insuficientes", None, None, "lateral")

    e_c = ema(closes, curta)
    e_m = ema(closes, media)
    e_l = ema(closes, longa)
    a = adx(highs, lows, closes, 14)
    adx_v = a.adx[-1]
    inc = slope_pct(e_m, 10, closes[-1])

    empilhada_alta = e_c[-1] is not None and e_m[-1] is not None and e_l[-1] is not None and e_c[-1] > e_m[-1] > e_l[-1]
    empilhada_baixa = e_c[-1] is not None and e_m[-1] is not None and e_l[-1] is not None and e_c[-1] < e_m[-1] < e_l[-1]

    # estrutura por pivos: topos e fundos ascendentes / descendentes
    ps = pivos(candles, 3, 3)
    topos = [p.preco for p in ps if p.tipo == "topo"][-3:]
    fundos = [p.preco for p in ps if p.tipo == "fundo"][-3:]
    estrutura = "lateral"
    if len(topos) >= 2 and len(fundos) >= 2:
        if topos[-1] > topos[-2] and fundos[-1] > fundos[-2]:
            estrutura = "alta"
        elif topos[-1] < topos[-2] and fundos[-1] < fundos[-2]:
            estrutura = "baixa"

    pontos_alta = sum([empilhada_alta, estrutura == "alta", (inc or 0) > 0.01, closes[-1] > (e_m[-1] or closes[-1])])
    pontos_baixa = sum([empilhada_baixa, estrutura == "baixa", (inc or 0) < -0.01, closes[-1] < (e_m[-1] or closes[-1])])

    if pontos_alta >= 3 and pontos_alta > pontos_baixa:
        direcao = Direction.LONG
        base = pontos_alta / 4.0
    elif pontos_baixa >= 3 and pontos_baixa > pontos_alta:
        direcao = Direction.SHORT
        base = pontos_baixa / 4.0
    else:
        direcao = None
        base = 0.0

    forca_adx = 0.0 if adx_v is None else min(max((adx_v - 15.0) / 20.0, 0.0), 1.0)
    forca = round(min(1.0, base * 0.65 + forca_adx * 0.35), 3) if direcao else round(forca_adx * 0.2, 3)

    if direcao is Direction.LONG:
        desc = f"tendencia de alta ({estrutura}, ADX {adx_v:.0f})" if adx_v else "tendencia de alta"
    elif direcao is Direction.SHORT:
        desc = f"tendencia de baixa ({estrutura}, ADX {adx_v:.0f})" if adx_v else "tendencia de baixa"
    else:
        desc = f"lateral/indefinida (ADX {adx_v:.0f})" if adx_v else "lateral/indefinida"
    return Tendencia(direcao, forca, desc, adx_v, inc, estrutura)


class Fibonacci(NamedTuple):
    inicio: float
    fim: float
    direcao: Direction  # direcao da perna impulsiva
    retracoes: dict[str, float]
    extensoes: dict[str, float]


def perna_impulsiva(candles: Sequence[Candle], lookback: int = 90) -> Optional[tuple[int, int]]:
    """Encontra a ultima perna impulsiva relevante (maior deslocamento recente)."""
    janela = candles[-lookback:]
    if len(janela) < 10:
        return None
    base = len(candles) - len(janela)
    i_max = max(range(len(janela)), key=lambda i: janela[i].high)
    i_min = min(range(len(janela)), key=lambda i: janela[i].low)
    return (base + i_min, base + i_max) if i_min < i_max else (base + i_max, base + i_min)


def fibonacci(candles: Sequence[Candle], lookback: int = 90) -> Optional[Fibonacci]:
    """Retracoes e extensoes de Fibonacci da ultima perna impulsiva."""
    perna = perna_impulsiva(candles, lookback)
    if not perna:
        return None
    i0, i1 = perna
    if candles[i0].low < candles[i1].low:
        inicio, fim, direcao = candles[i0].low, candles[i1].high, Direction.LONG
    else:
        inicio, fim, direcao = candles[i0].high, candles[i1].low, Direction.SHORT
    amp = fim - inicio
    if amp == 0:
        return None
    retr = {f"{p:.3f}": fim - amp * p for p in (0.236, 0.382, 0.5, 0.618, 0.786)}
    ext = {f"{p:.3f}": fim + amp * (p - 1.0) for p in (1.272, 1.414, 1.618, 2.0)}
    return Fibonacci(inicio, fim, direcao, retr, ext)


class NiveisDia(NamedTuple):
    abertura: Optional[float]
    maxima: Optional[float]
    minima: Optional[float]
    fechamento_anterior: Optional[float]
    maxima_anterior: Optional[float]
    minima_anterior: Optional[float]
    or_high: Optional[float]  # range de abertura (primeiros minutos)
    or_low: Optional[float]
    pivot: Optional[float]
    r1: Optional[float]
    s1: Optional[float]


def niveis_do_dia(candles: Sequence[Candle], minutos_or: int = 15) -> NiveisDia:
    """Niveis classicos do dia: abertura, maxima/minima, dia anterior, range de abertura e pivot."""
    if not candles:
        return NiveisDia(*([None] * 11))
    grupos: list[list[Candle]] = []
    dia = None
    for c in candles:
        d = c.ts.astimezone(BRT).date()
        if d != dia:
            grupos.append([])
            dia = d
        grupos[-1].append(c)
    hoje = grupos[-1]
    ontem = grupos[-2] if len(grupos) > 1 else []

    abertura = hoje[0].open
    maxima = max(c.high for c in hoje)
    minima = min(c.low for c in hoje)
    fech_ant = ontem[-1].close if ontem else None
    max_ant = max(c.high for c in ontem) if ontem else None
    min_ant = min(c.low for c in ontem) if ontem else None

    inicio = hoje[0].ts
    ors = [c for c in hoje if (c.ts - inicio).total_seconds() < minutos_or * 60]
    or_high = max(c.high for c in ors) if ors else None
    or_low = min(c.low for c in ors) if ors else None

    pivot = r1 = s1 = None
    if ontem:
        pivot = (max_ant + min_ant + fech_ant) / 3.0
        r1 = 2 * pivot - min_ant
        s1 = 2 * pivot - max_ant
    return NiveisDia(abertura, maxima, minima, fech_ant, max_ant, min_ant, or_high, or_low, pivot, r1, s1)
