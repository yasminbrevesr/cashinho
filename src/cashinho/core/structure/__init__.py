"""Leitura objetiva da estrutura de precos.

Identifica pivos, swing highs/lows, topos e fundos, classifica tendencia de
alta, de baixa ou lateralizacao, monta suportes e resistencias, detecta
rompimento, possivel falso rompimento e pullback - e so entao, quando existe
um swing valido, desenha a grade de Fibonacci.

    from cashinho.core.structure import analisar_estrutura, painel

    estrutura = analisar_estrutura(serie_5m)
    print(painel(estrutura))
"""

from .analysis import analisar_camada, analisar_estrutura
from .config import PADRAO, EstruturaConfig
from .fibonacci import constroi as constroi_fibonacci
from .fibonacci import preco_da_razao
from .models import (
    EventoEstrutura,
    FibGrid,
    FibLevel,
    FibZone,
    Level,
    MarketStructure,
    Pivot,
    Regime,
    Swing,
    Tendencia,
    TipoEvento,
    TipoPivo,
)
from .view import grafico, painel, resumo

__all__ = [
    "analisar_estrutura",
    "analisar_camada",
    "EstruturaConfig",
    "PADRAO",
    "MarketStructure",
    "Pivot",
    "Swing",
    "Level",
    "Tendencia",
    "Regime",
    "EventoEstrutura",
    "TipoEvento",
    "TipoPivo",
    "FibGrid",
    "FibLevel",
    "FibZone",
    "constroi_fibonacci",
    "preco_da_razao",
    "painel",
    "grafico",
    "resumo",
]
