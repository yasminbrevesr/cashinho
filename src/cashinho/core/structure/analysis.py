"""Ponto de entrada: le uma serie de candles e devolve a estrutura completa."""

from __future__ import annotations

from typing import Optional

from ...indicators.core import atr as calcula_atr
from ...models import Series
from . import fibonacci
from .config import PADRAO, EstruturaConfig
from .events import detecta_eventos
from .levels import constroi_niveis, separa
from .models import MarketStructure, Regime, Tendencia, TipoPivo
from .pivots import (
    detecta_pivos,
    filtra_significativos,
    monta_swings,
    ultimo_swing_valido,
)
from .trend import classifica


def analisar_estrutura(serie: Series, cfg: EstruturaConfig = PADRAO) -> MarketStructure:
    """Leitura completa da estrutura de precos da serie.

    A serie deve conter apenas candles FECHADOS (e' o que a vista do motor
    multi-timeframe entrega). Tudo o que sai daqui - pivos, niveis, eventos e
    Fibonacci - se refere ao ultimo candle da serie.
    """
    if len(serie) == 0:
        raise ValueError("serie vazia: nao ha estrutura para ler")

    preco = serie.price
    atr_valor = _atr_de_referencia(serie, cfg)

    minimo = cfg.pivo_esquerda + cfg.pivo_direita + 1
    if len(serie) < minimo:
        return _estrutura_vazia(serie, preco, atr_valor, f"serie com {len(serie)} candles (minimo {minimo})")

    serie_atr = calcula_atr(serie.highs, serie.lows, serie.closes, cfg.atr_periodo)
    pivos = detecta_pivos(serie, cfg, serie_atr)
    significativos = filtra_significativos(pivos, preco, atr_valor, cfg) if pivos else []

    swing_highs = [p for p in significativos if p.tipo is TipoPivo.TOPO]
    swing_lows = [p for p in significativos if p.tipo is TipoPivo.FUNDO]
    swings = monta_swings(significativos, preco, atr_valor, cfg)
    swing_valido = ultimo_swing_valido(swings)

    tendencia = classifica(swing_highs, swing_lows, preco, atr_valor, cfg)
    niveis = constroi_niveis(pivos, serie, preco, atr_valor, cfg)
    suportes, resistencias, zona_atual = separa(niveis, preco, cfg)
    eventos = detecta_eventos(serie, niveis, tendencia, swing_valido, atr_valor, cfg)

    grade = fibonacci.constroi(swing_valido, niveis, atr_valor, cfg)
    motivo = "" if grade else fibonacci.motivo_da_ausencia(swings, bool(pivos))

    return MarketStructure(
        symbol=serie.symbol,
        timeframe=serie.timeframe,
        ts=serie.last.ts,
        preco=preco,
        atr=atr_valor,
        pivos=pivos,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        swings=swings,
        tendencia=tendencia,
        suportes=suportes,
        resistencias=resistencias,
        eventos=eventos,
        swing_valido=swing_valido,
        fib=grade,
        motivo_sem_fib=motivo,
        zona_atual=zona_atual,
    )


def analisar_camada(vista, papel: str, cfg: EstruturaConfig = PADRAO) -> MarketStructure:
    """Le a estrutura de uma camada do motor multi-timeframe.

    Como a vista so entrega candles fechados, a leitura fica automaticamente
    livre de lookahead::

        estrutura = analisar_camada(engine.em(agora), "setup")
    """
    return analisar_estrutura(vista.serie_da_camada(papel), cfg)


def _atr_de_referencia(serie: Series, cfg: EstruturaConfig) -> float:
    """ATR atual; se a serie for curta demais, cai para o range medio."""
    valores = calcula_atr(serie.highs, serie.lows, serie.closes, cfg.atr_periodo)
    atual = valores[-1] if valores else None
    if atual:
        return atual
    ranges = [c.range for c in serie.candles if c.range > 0]
    if ranges:
        return sum(ranges) / len(ranges)
    return max(serie.price * 0.01, 1e-6)


def _estrutura_vazia(serie: Series, preco: float, atr_valor: float, motivo: str) -> MarketStructure:
    return MarketStructure(
        symbol=serie.symbol,
        timeframe=serie.timeframe,
        ts=serie.last.ts,
        preco=preco,
        atr=atr_valor,
        pivos=[],
        swing_highs=[],
        swing_lows=[],
        swings=[],
        tendencia=Tendencia(
            regime=Regime.LATERAL,
            forca=0.0,
            sequencia="-",
            descricao=f"estrutura indisponivel: {motivo}",
        ),
        suportes=[],
        resistencias=[],
        eventos=[],
        motivo_sem_fib=f"sem pivos confirmados: {motivo}",
    )
