"""Um MetaTrader5 de mentira - fiel ao que a maquina real devolveu."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from cashinho.data.metatrader.terminal import TerminalMT5
from cashinho.models import BRT

# uma quinta-feira as 17:32, dentro do pregao - o horario do teste real
AGORA = datetime(2026, 8, 20, 17, 32, 45, tzinfo=BRT)

SIMBOLOS_GENIAL = ("PETR4", "PETR4F", "PETR4T", "PETR4M", "PETR4Q", "PETR4R",
                   "VALE3", "ITUB4")


def epoch_do_servidor(momento: datetime) -> float:
    """O numero que o MT5 devolveria para esse relogio de parede."""
    ingenuo = momento.astimezone(BRT).replace(tzinfo=None)
    return ingenuo.replace(tzinfo=timezone.utc).timestamp()


def tick_de_cotacao(bid: float = 42.06, ask: float = 42.07,
                    momento: Optional[datetime] = None) -> dict:
    quando = momento or (AGORA - timedelta(seconds=4))
    return {"time": int(epoch_do_servidor(quando)),
            "time_msc": int(epoch_do_servidor(quando) * 1000) + 596,
            "bid": bid, "ask": ask, "last": 0.0, "volume": 0}


def tick_de_negocio(last: float = 42.07, volume: float = 400,
                    momento: Optional[datetime] = None) -> dict:
    quando = momento or (AGORA - timedelta(seconds=4))
    return {"time": int(epoch_do_servidor(quando)),
            "time_msc": int(epoch_do_servidor(quando) * 1000) + 601,
            "bid": 0.0, "ask": 0.0, "last": last, "volume": volume}


def candle(minutos_atras: int, timeframe_min: int = 1, preco: float = 42.0) -> dict:
    quando = AGORA - timedelta(minutes=minutos_atras)
    # o MT5 marca o candle pela ABERTURA do periodo
    return {"time": int(epoch_do_servidor(quando)),
            "open": preco, "high": preco * 1.002, "low": preco * 0.998,
            "close": preco * 1.001, "tick_volume": 1200, "real_volume": 340_000,
            "spread": 1}


class MT5Falso:
    """Dublê da biblioteca MetaTrader5, com o comportamento observado."""

    def __init__(self, conectado: bool = True, simbolos: Sequence[str] = SIMBOLOS_GENIAL,
                 ticks_info: Optional[Sequence[dict]] = None,
                 ticks_trade: Optional[Sequence[dict]] = None,
                 candles: Optional[Sequence[dict]] = None,
                 initialize_ok: bool = True, tem_livro: bool = False,
                 erro: tuple = (0, "sem erro")):
        self._conectado = conectado
        self._simbolos = list(simbolos)
        self._ticks_info = list(ticks_info if ticks_info is not None else [tick_de_cotacao()])
        self._ticks_trade = list(ticks_trade if ticks_trade is not None else [tick_de_negocio()])
        self._candles = list(candles if candles is not None else
                             [candle(m) for m in range(5, 0, -1)])
        self._initialize_ok = initialize_ok
        self._tem_livro = tem_livro
        self._erro = erro
        self.selecionados: list[str] = []
        self.chamadas: list[str] = []

    # constantes da biblioteca
    COPY_TICKS_INFO = 1
    COPY_TICKS_TRADE = 2
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_D1 = 16408
    __version__ = "5.0.45"

    def initialize(self, caminho: str = "") -> bool:
        self.chamadas.append(f"initialize({caminho})")
        return self._initialize_ok

    def shutdown(self) -> None:
        self.chamadas.append("shutdown")

    def last_error(self):
        return self._erro

    def terminal_info(self):
        if not self._initialize_ok:
            return None
        return type("Info", (), {
            "connected": self._conectado,
            "company": "Genial Investimentos",
            "path": r"C:\Program Files\Genial Investimentos MetaTrader 5",
        })()

    def account_info(self):
        # a conta traz login e saldo; o adapter NAO pode expor isso
        return type("Conta", (), {"server": "GenialInvestimentos-PRD",
                                  "login": 123456, "balance": 98765.43})()

    def symbols_get(self):
        return [type("S", (), {"name": n})() for n in self._simbolos]

    def symbol_info(self, symbol: str):
        if symbol not in self._simbolos:
            return None
        return type("S", (), {"name": symbol, "visible": True, "digits": 2})()

    def symbol_select(self, symbol: str, ativar: bool) -> bool:
        self.selecionados.append(symbol)
        return symbol in self._simbolos

    def copy_ticks_from(self, symbol, desde, quantidade, tipo):
        self.chamadas.append(f"copy_ticks_from({symbol}, {tipo})")
        if tipo == self.COPY_TICKS_INFO:
            return list(self._ticks_info)
        return list(self._ticks_trade)

    def copy_rates_from_pos(self, symbol, timeframe, inicio, quantidade):
        self.chamadas.append(f"copy_rates_from_pos({symbol}, {timeframe})")
        return list(self._candles)[:quantidade]

    def market_book_add(self, symbol: str) -> bool:
        return self._tem_livro

    def market_book_get(self, symbol: str):
        return [{"type": 1, "price": 42.06, "volume": 100}] if self._tem_livro else None

    def market_book_release(self, symbol: str) -> bool:
        return True


class MT5Ausente:
    """Simula a biblioteca nao instalada (Linux, CI)."""


def terminal(mt5: Optional[MT5Falso] = None, caminho: str = "") -> TerminalMT5:
    return TerminalMT5(caminho, mt5=mt5 if mt5 is not None else MT5Falso())


def provedor(mt5: Optional[MT5Falso] = None, agora: datetime = AGORA, **campos):
    from cashinho.data.metatrader import MetaTraderMarketDataProvider
    from cashinho.settings import ConfigMarketData

    config = ConfigMarketData(**campos) if campos else ConfigMarketData()
    p = MetaTraderMarketDataProvider(config, terminal=terminal(mt5),
                                     relogio=lambda: agora)
    p.conectar()
    return p
