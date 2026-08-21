"""Motor multi-timeframe do Cashinho.

Alinha os timeframes de contexto (60m), tendencia (15m), setup (5m) e gatilho
(1m) - combinacao configuravel - garantindo que um timeframe superior so seja
consultado depois que o candle dele fechou.
"""

from .config import CAMADAS_PADRAO, MTFConfig
from .engine import MTFEngine, MTFVista
from .errors import (
    ConfiguracaoInvalidaError,
    DadosInsuficientesError,
    LookaheadError,
    MTFError,
)
from .resample import janela, janela_do_candle, para_bars, reamostrar
from .session import SESSAO_B3, SESSAO_B3_COM_LEILAO, SESSAO_WIN, Sessao
from .timeframes import Bar, Timeframe, bars_para_series, parse_timeframe, rotulo_canonico

__all__ = [
    "MTFConfig",
    "CAMADAS_PADRAO",
    "MTFEngine",
    "MTFVista",
    "MTFError",
    "LookaheadError",
    "DadosInsuficientesError",
    "ConfiguracaoInvalidaError",
    "Sessao",
    "SESSAO_B3",
    "SESSAO_B3_COM_LEILAO",
    "SESSAO_WIN",
    "Timeframe",
    "parse_timeframe",
    "rotulo_canonico",
    "Bar",
    "bars_para_series",
    "reamostrar",
    "para_bars",
    "janela",
    "janela_do_candle",
]
