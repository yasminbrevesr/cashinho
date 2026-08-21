"""Pivos, swing highs/lows e pernas de swing.

O criterio e' mecanico: um pivo de topo e' um candle cuja maxima nao e'
superada por ``esquerda`` candles antes nem por ``direita`` candles depois.
So depois desses ``direita`` candles o pivo passa a existir - e' o que
``indice_confirmacao`` registra, para que nenhuma leitura use um pivo que
ainda nao tinha sido confirmado naquele instante.

Do fractal cru para a estrutura util ha dois filtros:

1. **alternancia** - topos e fundos precisam se revezar; sequencias de topos
   seguidos colapsam no mais alto (e fundos seguidos, no mais baixo);
2. **significancia** - pernas menores que ``swing_min_atr`` (ou que
   ``swing_min_pct`` do preco) sao ruido e desaparecem.

O que sobra sao os swing highs e swing lows: os extremos que realmente
sustentam a leitura de tendencia e ancoram o Fibonacci.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Series
from .config import PADRAO, EstruturaConfig
from .models import Pivot, Swing, TipoPivo


def detecta_pivos(
    serie: Series,
    cfg: EstruturaConfig = PADRAO,
    atr: Optional[Sequence[Optional[float]]] = None,
) -> list[Pivot]:
    """Fractais crus de topo e fundo, ja com o candle que os confirma."""
    candles = serie.candles
    n = len(candles)
    esq, dir_ = cfg.pivo_esquerda, cfg.pivo_direita
    saida: list[Pivot] = []
    if n < esq + dir_ + 1:
        return saida

    for i in range(esq, n - dir_):
        c = candles[i]
        janela_esq = candles[i - esq : i]
        janela_dir = candles[i + 1 : i + dir_ + 1]

        eh_topo = all(x.high <= c.high for x in janela_esq) and all(x.high < c.high for x in janela_dir)
        eh_fundo = all(x.low >= c.low for x in janela_esq) and all(x.low > c.low for x in janela_dir)

        if not (eh_topo or eh_fundo):
            continue

        ref = _atr_em(atr, i) or _range_medio(candles, i, esq + dir_ + 1)
        confirmacao = candles[i + dir_]
        vizinhanca = candles[i - esq : i + dir_ + 1]

        if eh_topo:
            proeminencia = (c.high - min(x.low for x in vizinhanca)) / ref if ref else 0.0
            saida.append(
                Pivot(
                    indice=i,
                    ts=c.ts,
                    preco=c.high,
                    tipo=TipoPivo.TOPO,
                    indice_confirmacao=i + dir_,
                    ts_confirmacao=confirmacao.ts,
                    proeminencia_atr=round(proeminencia, 3),
                )
            )
        if eh_fundo:
            proeminencia = (max(x.high for x in vizinhanca) - c.low) / ref if ref else 0.0
            saida.append(
                Pivot(
                    indice=i,
                    ts=c.ts,
                    preco=c.low,
                    tipo=TipoPivo.FUNDO,
                    indice_confirmacao=i + dir_,
                    ts_confirmacao=confirmacao.ts,
                    proeminencia_atr=round(proeminencia, 3),
                )
            )

    saida.sort(key=lambda p: (p.indice, p.tipo.value))
    return saida


def _atr_em(atr: Optional[Sequence[Optional[float]]], i: int) -> Optional[float]:
    if not atr or i >= len(atr):
        return None
    return atr[i]


def _range_medio(candles, i: int, janela: int) -> float:
    trecho = candles[max(i - janela, 0) : i + 1]
    if not trecho:
        return 0.0
    return sum(c.range for c in trecho) / len(trecho)


# ---------------------------------------------------------------------------
# alternancia e significancia
# ---------------------------------------------------------------------------


def alterna(pivos: Sequence[Pivot]) -> list[Pivot]:
    """Forca o revezamento topo/fundo, mantendo o extremo de cada sequencia."""
    saida: list[Pivot] = []
    for p in sorted(pivos, key=lambda x: x.indice):
        if saida and saida[-1].tipo is p.tipo:
            anterior = saida[-1]
            melhor = (
                p
                if (p.eh_topo and p.preco > anterior.preco) or (p.eh_fundo and p.preco < anterior.preco)
                else anterior
            )
            saida[-1] = melhor
        else:
            saida.append(p)
    return saida


def filtra_significativos(
    pivos: Sequence[Pivot],
    preco_ref: float,
    atr: float,
    cfg: EstruturaConfig = PADRAO,
) -> list[Pivot]:
    """Remove pernas de ruido ate sobrar so o que move a estrutura (zigzag).

    Uma perna abaixo do limiar nao vira estrutura: os dois pivos que a formam
    caem juntos, o que preserva a alternancia, e os vizinhos se fundem no
    extremo mais relevante.
    """
    limiar = limiar_swing(preco_ref, atr, cfg)
    seq = alterna(pivos)

    mudou = True
    while mudou and len(seq) > 2:
        mudou = False
        for i in range(len(seq) - 1):
            if abs(seq[i + 1].preco - seq[i].preco) >= limiar:
                continue
            # nao descarta a ultima perna se ela for a unica estrutura viva
            if len(seq) <= 3:
                break
            seq = alterna(seq[:i] + seq[i + 2 :])
            mudou = True
            break

    return [
        Pivot(
            indice=p.indice,
            ts=p.ts,
            preco=p.preco,
            tipo=p.tipo,
            indice_confirmacao=p.indice_confirmacao,
            ts_confirmacao=p.ts_confirmacao,
            proeminencia_atr=p.proeminencia_atr,
            significativo=True,
        )
        for p in seq
    ]


def limiar_swing(preco_ref: float, atr: float, cfg: EstruturaConfig = PADRAO) -> float:
    """Amplitude minima para uma perna deixar de ser ruido."""
    por_atr = atr * cfg.swing_min_atr
    por_pct = preco_ref * cfg.swing_min_pct / 100.0
    return max(por_atr, por_pct)


def monta_swings(
    swings_pivos: Sequence[Pivot],
    preco_ref: float,
    atr: float,
    cfg: EstruturaConfig = PADRAO,
) -> list[Swing]:
    """Constroi as pernas entre pivos significativos consecutivos."""
    limiar = limiar_swing(preco_ref, atr, cfg)
    saida: list[Swing] = []
    for a, b in zip(swings_pivos, swings_pivos[1:]):
        amplitude = abs(b.preco - a.preco)
        valido = amplitude >= limiar
        saida.append(
            Swing(
                inicio=a,
                fim=b,
                amplitude=amplitude,
                amplitude_atr=round(amplitude / atr, 3) if atr else 0.0,
                amplitude_pct=round(amplitude / preco_ref * 100.0, 3) if preco_ref else 0.0,
                duracao=b.indice - a.indice,
                valido=valido,
                motivo="" if valido else (
                    f"amplitude {amplitude:.2f} abaixo do minimo {limiar:.2f}"
                ),
            )
        )
    return saida


def ultimo_swing_valido(swings: Sequence[Swing]) -> Optional[Swing]:
    """A perna valida mais recente - a unica que pode ancorar o Fibonacci."""
    for s in reversed(swings):
        if s.valido:
            return s
    return None
