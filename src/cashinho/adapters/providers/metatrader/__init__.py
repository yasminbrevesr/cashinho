"""Market Data em tempo real via MetaTrader 5 - somente leitura.

    from cashinho.adapters.providers.metatrader import MetaTraderMarketDataProvider

A biblioteca `MetaTrader5` so e importada dentro de `terminal`, e so quando
alguem realmente chama o terminal: em Linux, na CI e nos backtests o pacote
carrega normalmente e a ausencia dela vira estado descrito.
"""

from cashinho.adapters.providers.metatrader.broker_time import (
    DEFAULT_SERVER_TIMEZONE,
    BrokerTimeNormalizer,
    resolve_timezone,
)
from cashinho.adapters.providers.metatrader.provider import (
    PROVIDER_NAME,
    MetaTraderMarketDataProvider,
    MetaTraderProviderError,
)
from cashinho.adapters.providers.metatrader.symbols import (
    AmbiguousSymbolError,
    SymbolNotFoundError,
    SymbolResolution,
    resolve_symbol,
)
from cashinho.adapters.providers.metatrader.terminal import (
    TICKS_INFO,
    TICKS_TRADE,
    TIMEFRAME_CONSTANTS,
    MetaTraderError,
    MetaTraderTerminal,
    MetaTraderUnavailableError,
    TerminalInfo,
)

__all__ = [
    "DEFAULT_SERVER_TIMEZONE",
    "PROVIDER_NAME",
    "TICKS_INFO",
    "TICKS_TRADE",
    "TIMEFRAME_CONSTANTS",
    "AmbiguousSymbolError",
    "BrokerTimeNormalizer",
    "MetaTraderError",
    "MetaTraderMarketDataProvider",
    "MetaTraderProviderError",
    "MetaTraderTerminal",
    "MetaTraderUnavailableError",
    "SymbolNotFoundError",
    "SymbolResolution",
    "TerminalInfo",
    "resolve_symbol",
    "resolve_timezone",
]
