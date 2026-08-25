"""Cálculos reutilizáveis de resultado e exposição do modo PAPER."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from cashinho.pipeline.paper_broker import PaperOrder, PaperOrderStatus

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_CLOSED_STATUSES = {
    PaperOrderStatus.CLOSED,
    PaperOrderStatus.STOPPED,
    PaperOrderStatus.TARGETED,
}


@dataclass(frozen=True, slots=True)
class PaperPnL:
    """Resultado de uma posição PAPER, realizado ou marcado a mercado."""

    pnl_value: Decimal
    pnl_pct: Decimal
    result_in_r: Decimal
    risk_initial: Decimal
    duration: timedelta | None


@dataclass(frozen=True, slots=True)
class PaperSummary:
    """Resumo operacional derivado das ordens, nunca armazenado na UI."""

    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    exposed_risk: Decimal
    operations: int
    open_positions: int
    pending_orders: int
    unpriced_positions: int


def initial_risk(order: PaperOrder) -> Decimal:
    """Risco inicial usando o preço efetivo de execução quando disponível."""
    entry = order.fill_price or order.ticket.entry
    return (abs(entry - order.ticket.stop) * order.ticket.quantity).quantize(Decimal("0.01"))


def calculate_pnl(
    order: PaperOrder,
    *,
    exit_price: Decimal,
    realized: bool,
) -> PaperPnL:
    """Calcula P&L BUY/SELL sem consultar ou inventar preço de mercado."""
    if order.filled_at is None or order.fill_price is None:
        raise ValueError("P&L exige uma ordem PAPER executada.")
    exit_price = Decimal(exit_price)
    if exit_price <= 0:
        raise ValueError("Preço de saída deve ser maior que zero.")

    quantity = Decimal(order.ticket.quantity)
    direction = Decimal("1") if order.ticket.side == "BUY" else Decimal("-1")
    pnl = ((exit_price - order.fill_price) * quantity * direction).quantize(Decimal("0.01"))
    notional = abs(order.fill_price * quantity)
    pnl_pct = (pnl / notional * HUNDRED).quantize(Decimal("0.01")) if notional else ZERO
    risk = initial_risk(order)
    result_in_r = (pnl / risk).quantize(Decimal("0.01")) if risk else ZERO
    duration = None
    if realized:
        if order.closed_at is None:
            raise ValueError("Resultado realizado exige horário de encerramento.")
        duration = order.closed_at - order.filled_at
    return PaperPnL(pnl, pnl_pct, result_in_r, risk, duration)


def realized_pnl(order: PaperOrder) -> PaperPnL | None:
    if order.status not in _CLOSED_STATUSES or order.close_price is None:
        return None
    return calculate_pnl(order, exit_price=order.close_price, realized=True)


def unrealized_pnl(order: PaperOrder, market_price: Decimal | None) -> PaperPnL | None:
    if order.status is not PaperOrderStatus.OPEN or market_price is None:
        return None
    return calculate_pnl(order, exit_price=market_price, realized=False)


def summarize_orders(
    orders: list[PaperOrder],
    *,
    market_prices: dict[str, Decimal] | None = None,
    on_date: date | None = None,
) -> PaperSummary:
    """Consolida ordens PAPER; P&L aberto fica desconhecido sem preço válido."""
    market_prices = market_prices or {}
    open_orders = [order for order in orders if order.status is PaperOrderStatus.OPEN]
    pending_orders = [order for order in orders if order.status is PaperOrderStatus.PENDING]
    closed_orders = [
        order
        for order in orders
        if order.status in _CLOSED_STATUSES
        and (on_date is None or (order.closed_at is not None and order.closed_at.date() == on_date))
    ]
    operations = [
        order
        for order in orders
        if order.filled_at is not None
        and (on_date is None or order.filled_at.date() == on_date)
    ]
    realized = sum(
        (result.pnl_value for order in closed_orders if (result := realized_pnl(order)) is not None),
        ZERO,
    )
    valuations = [unrealized_pnl(order, market_prices.get(order.ticket.symbol)) for order in open_orders]
    known = [result for result in valuations if result is not None]
    unknown = len(valuations) - len(known)
    unrealized = None if unknown else sum((result.pnl_value for result in known), ZERO)
    return PaperSummary(
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        exposed_risk=sum((initial_risk(order) for order in open_orders), ZERO),
        operations=len(operations),
        open_positions=len(open_orders),
        pending_orders=len(pending_orders),
        unpriced_positions=unknown,
    )
