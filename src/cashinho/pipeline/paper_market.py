"""Marcação a mercado PAPER usando somente cotações reais disponíveis."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cashinho.domain.errors import CashinhoError
from cashinho.pipeline.paper_broker import PaperOrder, PaperOrderStatus
from cashinho.ports.clock import Clock
from cashinho.ports.market_data import MarketDataProvider


@dataclass(frozen=True, slots=True)
class PaperMarketSnapshot:
    market_prices: dict[str, Decimal]
    close_prices: dict[str, Decimal]
    errors: tuple[str, ...]


def collect_paper_market(
    provider: MarketDataProvider,
    orders: list[PaperOrder],
    *,
    clock: Clock | None = None,
    max_age_seconds: int = 60,
) -> PaperMarketSnapshot:
    """Obtém last para marcação e bid/ask para encerramento; sem fallback."""
    open_orders = [order for order in orders if order.status is PaperOrderStatus.OPEN]
    by_symbol = {order.ticket.symbol for order in open_orders}
    market_prices: dict[str, Decimal] = {}
    close_prices: dict[str, Decimal] = {}
    errors: list[str] = []
    for symbol in sorted(by_symbol):
        try:
            quote = provider.get_quote(symbol)
        except (CashinhoError, RuntimeError, ValueError) as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        if clock is not None:
            age = quote.age_seconds(clock)
            if age < 0 or age > max_age_seconds:
                errors.append(f"{symbol}: cotação sem atualidade suficiente para marcação PAPER.")
                continue
        if quote.price > 0:
            market_prices[symbol] = quote.price
        if not quote.has_active_book:
            errors.append(f"{symbol}: sem bid/ask ativo para encerramento PAPER.")
            continue
        for order in open_orders:
            if order.ticket.symbol != symbol:
                continue
            price = quote.bid if order.ticket.side == "BUY" else quote.ask
            if price is not None:
                close_prices[order.id] = price
    return PaperMarketSnapshot(market_prices, close_prices, tuple(errors))
