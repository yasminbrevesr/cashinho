from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cashinho.pipeline.paper_broker import PaperOrder, PaperOrderStatus, PaperOrderType
from cashinho.pipeline.paper_performance import realized_pnl, summarize_orders, unrealized_pnl
from cashinho.pipeline.paper_ticket import build_paper_ticket

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


def order(side: str, *, status: PaperOrderStatus, close: str | None = None) -> PaperOrder:
    stop, target = (("9", "12") if side == "BUY" else ("11", "8"))
    ticket = build_paper_ticket(
        symbol="PETR4",
        side=side,
        entry=Decimal("10"),
        stop=Decimal(stop),
        target=Decimal(target),
        quantity=10,
    )
    return PaperOrder(
        id=f"{side}-{status.value}",
        ticket=ticket,
        order_type=PaperOrderType.LIMIT,
        status=status,
        created_at=NOW - timedelta(minutes=5),
        filled_at=NOW,
        fill_price=Decimal("10"),
        closed_at=NOW + timedelta(minutes=15) if close else None,
        close_price=Decimal(close) if close else None,
        close_reason="TARGET" if close else None,
    )


def test_pnl_realizado_buy() -> None:
    result = realized_pnl(order("BUY", status=PaperOrderStatus.TARGETED, close="12"))
    assert result is not None
    assert result.pnl_value == Decimal("20.00")
    assert result.pnl_pct == Decimal("20.00")
    assert result.result_in_r == Decimal("2.00")
    assert result.duration == timedelta(minutes=15)


def test_pnl_realizado_sell() -> None:
    result = realized_pnl(order("SELL", status=PaperOrderStatus.TARGETED, close="8"))
    assert result is not None
    assert result.pnl_value == Decimal("20.00")
    assert result.result_in_r == Decimal("2.00")


def test_pnl_aberto_exige_preco_valido() -> None:
    opened = order("BUY", status=PaperOrderStatus.OPEN)
    assert unrealized_pnl(opened, None) is None
    assert unrealized_pnl(opened, Decimal("11")).pnl_value == Decimal("10.00")  # type: ignore[union-attr]


def test_resumo_nao_inventa_pnl_aberto() -> None:
    opened = order("BUY", status=PaperOrderStatus.OPEN)
    closed = order("SELL", status=PaperOrderStatus.TARGETED, close="8")
    summary = summarize_orders([opened, closed], on_date=NOW.date())
    assert summary.realized_pnl == Decimal("20.00")
    assert summary.unrealized_pnl is None
    assert summary.unpriced_positions == 1
    assert summary.exposed_risk == Decimal("10.00")


def test_resumo_com_marcacao_real() -> None:
    opened = order("BUY", status=PaperOrderStatus.OPEN)
    summary = summarize_orders(
        [opened], market_prices={"PETR4": Decimal("11")}, on_date=NOW.date()
    )
    assert summary.unrealized_pnl == Decimal("10.00")
    assert summary.open_positions == 1
