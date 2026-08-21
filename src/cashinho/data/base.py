"""Contrato dos provedores de dados de mercado."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from ..models import Series


class DataError(RuntimeError):
    """Erro ao obter dados de mercado."""


class Provider(ABC):
    """Fonte de candles. Implemente para plugar outra corretora/feed."""

    nome: str = "base"

    @abstractmethod
    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        """Devolve a serie de candles do ativo no timeframe pedido.

        ``timeframe`` usa a notacao ``1m``, ``5m``, ``15m``, ``30m``, ``60m``, ``1d``.
        """

    def multiplos(self, symbols: Iterable[str], timeframe: str, dias: int = 5) -> dict[str, Series]:
        out: dict[str, Series] = {}
        for s in symbols:
            try:
                out[s] = self.candles(s, timeframe, dias)
            except DataError:
                continue
        return out

    def preco_atual(self, symbol: str) -> Optional[float]:
        try:
            s = self.candles(symbol, "5m", 1)
        except DataError:
            return None
        return s.price if len(s) else None


TIMEFRAME_MINUTOS = {
    "1m": 1,
    "2m": 2,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1h": 60,
    "1d": 375,
}


def minutos_do_timeframe(tf: str) -> int:
    if tf not in TIMEFRAME_MINUTOS:
        raise DataError(f"timeframe nao suportado: {tf}")
    return TIMEFRAME_MINUTOS[tf]
