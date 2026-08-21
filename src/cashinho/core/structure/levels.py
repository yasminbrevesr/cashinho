"""Suportes e resistencias construidos a partir dos pivos.

Um nivel nao e' uma linha, e' uma faixa: pivos que caem dentro de uma
tolerancia (em ATR) viram a mesma zona. Quanto mais vezes o preco reagiu
naquela faixa, mais recente foi a ultima reacao e mais proeminentes foram os
pivos, maior a forca.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Series
from .config import PADRAO, EstruturaConfig
from .models import Level, Pivot


def constroi_niveis(
    pivos: Sequence[Pivot],
    serie: Series,
    preco: float,
    atr: float,
    cfg: EstruturaConfig = PADRAO,
) -> list[Level]:
    """Agrupa pivos proximos em zonas e mede a forca de cada uma."""
    if not pivos or atr <= 0:
        return []

    n = len(serie)
    corte = n - cfg.lookback_niveis
    recentes = [p for p in pivos if p.indice >= corte]
    if not recentes:
        return []

    tolerancia = atr * cfg.tolerancia_nivel_atr
    clusters: list[list[Pivot]] = []
    for p in sorted(recentes, key=lambda x: x.preco):
        if clusters and p.preco - _media(clusters[-1]) <= tolerancia:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    niveis: list[Level] = []
    for grupo in clusters:
        precos = [p.preco for p in grupo]
        low, high = min(precos), max(precos)
        if high - low < tolerancia / 2:
            meio = (low + high) / 2
            low, high = meio - tolerancia / 4, meio + tolerancia / 4
        niveis.append(
            Level(
                low=low,
                high=high,
                tipo="resistencia" if (low + high) / 2 > preco else "suporte",
                toques=len(grupo),
                forca=_forca(grupo, n),
                ultimo_toque=max(p.ts for p in grupo),
                pivos=tuple(p.indice for p in grupo),
            )
        )
    return niveis


def _media(grupo: Sequence[Pivot]) -> float:
    return sum(p.preco for p in grupo) / len(grupo)


def _forca(grupo: Sequence[Pivot], n_candles: int) -> float:
    toques = min(len(grupo) / 3.0, 1.0)
    recencia = max(p.indice for p in grupo) / max(n_candles - 1, 1)
    proeminencia = min(sum(p.proeminencia_atr for p in grupo) / (len(grupo) * 2.0), 1.0)
    tem_os_dois_lados = len({p.tipo for p in grupo}) > 1  # virou suporte e resistencia
    forca = 0.35 * toques + 0.30 * recencia + 0.20 * proeminencia + (0.15 if tem_os_dois_lados else 0.0)
    return round(max(0.0, min(1.0, forca)), 3)


def separa(niveis: Sequence[Level], preco: float, cfg: EstruturaConfig = PADRAO):
    """Devolve ``(suportes, resistencias, zona_atual)`` ordenados por proximidade."""
    zona_atual: Optional[Level] = None
    suportes: list[Level] = []
    resistencias: list[Level] = []

    for nivel in niveis:
        if nivel.contem(preco):
            zona_atual = nivel if zona_atual is None or nivel.forca > zona_atual.forca else zona_atual
            continue
        if nivel.high < preco:
            suportes.append(nivel)
        else:
            resistencias.append(nivel)

    suportes.sort(key=lambda l: preco - l.high)
    resistencias.sort(key=lambda l: l.low - preco)
    return (
        suportes[: cfg.max_niveis_por_lado],
        resistencias[: cfg.max_niveis_por_lado],
        zona_atual,
    )


def nivel_mais_proximo(niveis: Sequence[Level], preco: float) -> Optional[Level]:
    if not niveis:
        return None
    return min(niveis, key=lambda l: l.distancia(preco))
