"""Porta de dados de mercado.

Estrategias nunca conhecem Yahoo Finance, MetaTrader, Genial ou qualquer
outro fornecedor. Elas conhecem esta interface.

`ProviderCapabilities` implementa a decisao D9: a capacidade declarada do
provedor limita quais modos podem usa-lo. Um provedor com cotacao atrasada
nao habilita decisao intradiaria ao vivo, e o bloqueio e estrutural em vez
de depender de disciplina do operador.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import Field

from cashinho.domain.enums import Mode, Timeframe
from cashinho.domain.market import CandleSeries, Quote
from cashinho.domain.types import DomainModel


class ProviderCapabilities(DomainModel):
    """O que um provedor de dados consegue efetivamente entregar."""

    name: str
    supports_realtime: bool = False
    typical_delay_seconds: int = Field(default=0, ge=0)
    min_timeframe: Timeframe = Timeframe.D1
    intraday_history_days: int = Field(default=0, ge=0)
    supports_quotes: bool = False
    notes: str = ""

    def supports(self, timeframe: Timeframe) -> bool:
        """Se o provedor entrega o timeframe pedido."""
        return timeframe.duration >= self.min_timeframe.duration

    def allows_mode(self, mode: Mode) -> bool:
        """Se o provedor e adequado ao modo de operacao."""
        if mode.requires_realtime_data:
            return self.supports_realtime
        return True

    def rejection_reason(self, mode: Mode, timeframe: Timeframe) -> str | None:
        """Motivo textual da incompatibilidade, ou None se compativel."""
        if not self.allows_mode(mode):
            return (
                f"provider '{self.name}' nao fornece dado em tempo real "
                f"(atraso tipico {self.typical_delay_seconds}s) e o modo {mode} exige"
            )
        if not self.supports(timeframe):
            return (
                f"provider '{self.name}' nao fornece timeframe {timeframe} "
                f"(minimo disponivel: {self.min_timeframe})"
            )
        return None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Fonte de dados de mercado."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Declaracao do que este provedor entrega."""
        ...

    def get_available_timeframes(self, symbol: str) -> tuple[Timeframe, ...]:
        """Timeframes efetivamente disponiveis para o ativo.

        Diferente de `capabilities.min_timeframe`, que e uma declaracao
        geral do provedor: aqui a resposta e por ativo, porque cobertura
        de historico intradiario costuma variar entre papeis.
        """
        ...

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        start: datetime,
        end: datetime,
    ) -> CandleSeries:
        """Candles do intervalo pedido, em ordem cronologica.

        Intervalo semiaberto `[start, end)` sobre `open_time`. A serie
        retornada carrega procedencia e instante de coleta.
        """
        ...

    def get_quote(self, symbol: str) -> Quote:
        """Cotacao mais recente disponivel, com procedencia e latencia."""
        ...
