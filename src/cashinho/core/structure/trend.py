"""Classificacao de tendencia pela sequencia de topos e fundos.

Regra unica e verificavel:

- **alta**: topo mais alto que o anterior E fundo mais alto que o anterior
  (HH/HL);
- **baixa**: topo mais baixo E fundo mais baixo (LH/LL);
- **lateralizacao**: qualquer outra combinacao (inclusive HH/LL, que e'
  expansao de volatilidade, e LH/HL, que e' compressao).

A comparacao usa uma tolerancia em ATR para que diferenca de centavos entre
dois topos nao vire "topo ascendente".
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .config import PADRAO, EstruturaConfig
from .models import Pivot, Regime, Tendencia


def _compara(atual: float, anterior: float, tolerancia: float) -> str:
    if atual > anterior + tolerancia:
        return "maior"
    if atual < anterior - tolerancia:
        return "menor"
    return "igual"


def _pares_confirmando(precos: Sequence[float], sentido: str, tolerancia: float) -> int:
    """Quantos pares consecutivos seguem o mesmo sentido, do mais recente para tras."""
    contador = 0
    for i in range(len(precos) - 1, 0, -1):
        if _compara(precos[i], precos[i - 1], tolerancia) == sentido:
            contador += 1
        else:
            break
    return contador


def classifica(
    swing_highs: Sequence[Pivot],
    swing_lows: Sequence[Pivot],
    preco: float,
    atr: float,
    cfg: EstruturaConfig = PADRAO,
) -> Tendencia:
    """Le a estrutura e devolve regime, forca e a sequencia encontrada."""
    topos = tuple(swing_highs)
    fundos = tuple(swing_lows)
    tolerancia = atr * cfg.tolerancia_estrutura_atr

    if len(topos) < 2 or len(fundos) < 2:
        return Tendencia(
            regime=Regime.LATERAL,
            forca=0.0,
            sequencia="-",
            descricao="estrutura insuficiente: menos de dois topos ou dois fundos confirmados",
            topos=topos,
            fundos=fundos,
            range_low=min((f.preco for f in fundos), default=None),
            range_high=max((t.preco for t in topos), default=None),
        )

    cmp_topos = _compara(topos[-1].preco, topos[-2].preco, tolerancia)
    cmp_fundos = _compara(fundos[-1].preco, fundos[-2].preco, tolerancia)

    rotulo_topo = {"maior": "HH", "menor": "LH", "igual": "=H"}[cmp_topos]
    rotulo_fundo = {"maior": "HL", "menor": "LL", "igual": "=L"}[cmp_fundos]
    sequencia = f"{rotulo_topo}/{rotulo_fundo}"

    range_low = min(f.preco for f in fundos[-3:])
    range_high = max(t.preco for t in topos[-3:])
    amplitude_atr = (range_high - range_low) / atr if atr else 0.0

    if cmp_topos == "maior" and cmp_fundos == "maior":
        regime = Regime.ALTA
    elif cmp_topos == "menor" and cmp_fundos == "menor":
        regime = Regime.BAIXA
    else:
        regime = Regime.LATERAL

    if regime is Regime.LATERAL:
        forca = _forca_lateral(amplitude_atr, cfg)
        if sequencia in ("HH/LL", "=H/=L"):
            detalhe = "topos e fundos abrindo (expansao)" if sequencia == "HH/LL" else "topos e fundos parados"
        elif sequencia == "LH/HL":
            detalhe = "topos e fundos comprimindo (triangulo)"
        else:
            detalhe = "sem sequencia definida"
        descricao = (
            f"lateralizacao entre {formata_dinheiro(range_low)} e {formata_dinheiro(range_high)} "
            f"({amplitude_atr:.1f} ATR de amplitude) - {detalhe} [{sequencia}]"
        )
        return Tendencia(regime, forca, sequencia, descricao, topos, fundos, range_low, range_high)

    sentido = "maior" if regime is Regime.ALTA else "menor"
    confirmacoes = min(
        _pares_confirmando([t.preco for t in topos], sentido, tolerancia),
        _pares_confirmando([f.preco for f in fundos], sentido, tolerancia),
    )
    forca = _forca_tendencia(confirmacoes, amplitude_atr, regime, preco, topos, fundos)
    palavra = "alta" if regime is Regime.ALTA else "baixa"
    descricao = (
        f"tendencia de {palavra}: {confirmacoes} perna(s) confirmando {sequencia}, "
        f"amplitude de {amplitude_atr:.1f} ATR"
    )
    return Tendencia(regime, forca, sequencia, descricao, topos, fundos, range_low, range_high)


def _forca_tendencia(
    confirmacoes: int,
    amplitude_atr: float,
    regime: Regime,
    preco: float,
    topos: Sequence[Pivot],
    fundos: Sequence[Pivot],
) -> float:
    forca = 0.45 + 0.15 * min(max(confirmacoes - 1, 0), 3)
    forca += 0.15 * min(amplitude_atr / 4.0, 1.0)
    referencia = fundos[-1].preco if regime is Regime.ALTA else topos[-1].preco
    respeitando = preco > referencia if regime is Regime.ALTA else preco < referencia
    forca += 0.15 if respeitando else -0.20
    return round(max(0.0, min(1.0, forca)), 3)


def _forca_lateral(amplitude_atr: float, cfg: EstruturaConfig) -> float:
    """Quanto mais estreito o range, mais 'lateral' e' a lateralizacao."""
    if amplitude_atr <= 0:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - amplitude_atr / cfg.lateral_max_atr)), 3)
