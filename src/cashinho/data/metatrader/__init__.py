"""Market Data em tempo real da Genial via MetaTrader 5 - somente leitura.

    from cashinho.data.metatrader import MetaTraderMarketDataProvider

    provedor = MetaTraderMarketDataProvider()
    provedor.conectar()
    provedor.cotacao("PETR4")

A biblioteca ``MetaTrader5`` so e' importada dentro de :mod:`terminal`, e so
quando alguem realmente chama o terminal - em Linux, na CI e nos backtests o
modulo carrega normalmente e a ausencia dela vira estado descrito.

**Nao envia ordem.** ``capacidades.trading`` e' falsa e nao existe metodo de
execucao nesta camada.
"""

from .provider import (
    EventoDeCotacao,
    EventoDeNegocio,
    MetaTraderMarketDataProvider,
)
from .simbolos import (
    Resolucao,
    SimboloAmbiguoError,
    SimboloNaoEncontradoError,
    resolver,
)
from .tempo import FUSO_PADRAO_DO_SERVIDOR, NormalizadorDeTempoDoBroker, fuso
from .terminal import (
    TICKS_INFO,
    TICKS_TRADE,
    TIMEFRAMES,
    InfoTerminal,
    MT5Error,
    MT5Indisponivel,
    TerminalMT5,
)

__all__ = [
    "MetaTraderMarketDataProvider", "EventoDeCotacao", "EventoDeNegocio",
    "TerminalMT5", "InfoTerminal", "MT5Error", "MT5Indisponivel",
    "TIMEFRAMES", "TICKS_INFO", "TICKS_TRADE",
    "NormalizadorDeTempoDoBroker", "fuso", "FUSO_PADRAO_DO_SERVIDOR",
    "resolver", "Resolucao", "SimboloNaoEncontradoError", "SimboloAmbiguoError",
]
