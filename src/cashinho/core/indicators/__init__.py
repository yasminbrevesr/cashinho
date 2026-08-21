"""Indicadores tecnicos.

Funcoes puras sobre `CandleSeries`. Nenhum indicador conhece Streamlit,
banco, provider ou estrategia, e nenhum deles emite sinal de compra ou
venda: devolvem numeros, e a interpretacao pertence as camadas de
estrategia, score e auditoria.

Nenhum indicador isolado deve criar uma oportunidade. A confluencia e
decidida adiante, com os resultados destes modulos como insumo.
"""

from cashinho.core.indicators.atr import atr, true_range
from cashinho.core.indicators.base import (
    IndicatorNotApplicableError,
    IndicatorResult,
    InsufficientDataError,
)
from cashinho.core.indicators.bollinger import bollinger
from cashinho.core.indicators.macd import macd
from cashinho.core.indicators.moving_average import ema, sma
from cashinho.core.indicators.rsi import rsi
from cashinho.core.indicators.vwap import VwapAnchor, typical_price, vwap

__all__ = [
    "IndicatorNotApplicableError",
    "IndicatorResult",
    "InsufficientDataError",
    "VwapAnchor",
    "atr",
    "bollinger",
    "ema",
    "macd",
    "rsi",
    "sma",
    "true_range",
    "typical_price",
    "vwap",
]
