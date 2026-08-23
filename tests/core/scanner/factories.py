"""Provedores e configuracoes para os testes do scanner."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence

from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.core.scanner import ScannerB3, ScannerConfig
from cashinho.data.base import DataError, Provider
from cashinho.data.synthetic import SyntheticProvider
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)


class ProviderDeTeste(Provider):
    """Devolve series preparadas por ativo - e erra nos que nao conhece."""

    nome = "teste"

    def __init__(self, series: Mapping[str, Series], falham: Sequence[str] = ()):
        self.series = {k.upper(): v for k, v in series.items()}
        self.falham = {a.upper() for a in falham}
        self.pedidos: list[str] = []

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        self.pedidos.append(symbol.upper())
        if symbol.upper() in self.falham:
            raise DataError(f"sem dados para {symbol}")
        try:
            return self.series[symbol.upper()]
        except KeyError as e:
            raise DataError(f"ativo desconhecido: {symbol}") from e


def serie(
    closes: Sequence[float],
    symbol: str = "PETR4",
    volumes: Optional[Sequence[float]] = None,
    pavio: float = 0.0015,
    inicio: Optional[datetime] = None,
) -> Series:
    inicio = inicio or ABERTURA
    candles = []
    anterior = closes[0]
    for i, c in enumerate(closes):
        candles.append(
            Candle(inicio + timedelta(minutes=i), anterior,
                   max(anterior, c) * (1 + pavio), min(anterior, c) * (1 - pavio), c,
                   volumes[i] if volumes else 200_000.0)
        )
        anterior = c
    return Series(symbol, "1m", candles)


def serie_liquida(symbol: str = "PETR4", n: int = 300, passo: float = 0.0004) -> Series:
    """Serie que passa nos filtros: volume alto e volatilidade na faixa."""
    return serie([30.0 * (1 + passo) ** i for i in range(n)], symbol=symbol)


def serie_parada(symbol: str = "XXXX3", n: int = 300) -> Series:
    """Preco cravado: cortada pela volatilidade."""
    return serie([30.0] * n, symbol=symbol, pavio=0.0001)


def serie_sem_liquidez(symbol: str = "YYYY3", n: int = 300) -> Series:
    return serie([30.0 * (1 + 0.0004) ** i for i in range(n)], symbol=symbol,
                 volumes=[10.0] * n)


def serie_curta(symbol: str = "ZZZZ3", n: int = 30) -> Series:
    return serie([30.0] * n, symbol=symbol)


def risco_folgado(capital: float = 100_000.0) -> RiskManager:
    return RiskManager(
        RiskConfig(capital=capital, max_trades_dia=200, perda_max_diaria_pct=100.0,
                   max_perdas_consecutivas=200),
        RiskState(capital_inicial=capital),
    )


def scanner(
    provider: Optional[Provider] = None,
    config: Optional[ScannerConfig] = None,
    risco: Optional[RiskManager] = None,
    **campos_config,
) -> ScannerB3:
    base = dict(dias=3, atr_min_pct=0.05, liquidez_minima_diaria=1_000_000.0)
    base.update(campos_config)
    return ScannerB3(
        provider or SyntheticProvider(semente=4),
        config or ScannerConfig(**base),
        risco=risco or risco_folgado(),
    )
