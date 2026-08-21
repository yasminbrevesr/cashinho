"""Estrategias do Cashinho.

Uma estrategia recebe :class:`StrategyContext` e devolve :class:`Signal` -
so isso. Ela nao envia ordem, nao dimensiona posicao e nao fala com o Risk
Manager; apenas identifica uma condicao e explica a leitura.

    from cashinho.core.strategy import BaselineTendenciaVolumeATR, StrategyContext, tela_analise

    sinal = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_5m))
    print(tela_analise(sinal))

A estrategia ``baseline-tendencia`` existe para VALIDAR A ARQUITETURA: as
regras sao simples e nao passaram por otimizacao nem backtest. Ela nao e'
uma estrategia final de day trade.
"""

from .base import Strategy, disponiveis, obter, registrar
from .baseline import AVISO, BaselineConfig, BaselineTendenciaVolumeATR
from .context import StrategyContext, de_vista
from .models import Action, Factor, Signal
from .view import AVISO_CURTO, faixa_de_aviso, linha_de_lista, tela_analise

__all__ = [
    "Action",
    "Signal",
    "Factor",
    "Strategy",
    "StrategyContext",
    "de_vista",
    "BaselineTendenciaVolumeATR",
    "BaselineConfig",
    "AVISO",
    "AVISO_CURTO",
    "registrar",
    "obter",
    "disponiveis",
    "tela_analise",
    "linha_de_lista",
    "faixa_de_aviso",
]
