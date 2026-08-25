from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cashinho.domain.market import Candle, Quote
from cashinho.domain.risk import RiskProfile
from cashinho.pipeline.paper_broker import (
    InMemoryPaperOrderRepository,
    PaperBroker,
    PaperOrderStatus,
    PaperOrderType,
)
from cashinho.pipeline.paper_ticket import build_paper_ticket, calculate_ticket_sizing


def ticket(side: str = "BUY"):
    values = ("10", "9", "12") if side == "BUY" else ("10", "11", "8")
    return build_paper_ticket(
        symbol="PETR4",
        side=side,
        entry=Decimal(values[0]),
        stop=Decimal(values[1]),
        target=Decimal(values[2]),
        quantity=10,
        min_risk_reward=Decimal("2"),
        maximum_quantity=10,
    )


def candle(low: str, high: str) -> Candle:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    return Candle(
        open_time=now,
        close_time=now + timedelta(minutes=5),
        open=Decimal("10"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal("10"),
        volume=100,
        is_closed=True,
    )


def test_sizing_fracionario_e_recalculado() -> None:
    profile = RiskProfile(
        capital=Decimal("1000"),
        risk_per_trade_pct=Decimal("1"),
        max_exposure_per_symbol_pct=Decimal("20"),
    )
    sizing = calculate_ticket_sizing(
        entry=Decimal("30"), stop=Decimal("29"), profile=profile, lot_size=1
    )
    assert sizing.quantity == 6


def test_capital_pequeno_e_bloqueado() -> None:
    profile = RiskProfile(
        capital=Decimal("10"),
        risk_per_trade_pct=Decimal("1"),
        max_exposure_per_symbol_pct=Decimal("1"),
    )
    with pytest.raises(ValueError, match="nem uma acao"):
        calculate_ticket_sizing(entry=Decimal("30"), stop=Decimal("29"), profile=profile)


@pytest.mark.parametrize(
    ("side", "entry", "stop", "target"),
    [("BUY", "10", "11", "12"), ("SELL", "10", "9", "8")],
)
def test_geometria_invalida(side: str, entry: str, stop: str, target: str) -> None:
    with pytest.raises(ValueError, match="Geometria"):
        build_paper_ticket(
            symbol="X",
            side=side,
            entry=Decimal(entry),
            stop=Decimal(stop),
            target=Decimal(target),
            quantity=1,
        )


def test_quantidade_acima_do_risco_e_bloqueada() -> None:
    with pytest.raises(ValueError, match="Risk Manager"):
        build_paper_ticket(
            symbol="X",
            side="BUY",
            entry=Decimal("10"),
            stop=Decimal("9"),
            target=Decimal("12"),
            quantity=11,
            maximum_quantity=10,
        )


def test_ordem_limitada_e_oco() -> None:
    broker = PaperBroker(InMemoryPaperOrderRepository())
    order = broker.register(ticket(), PaperOrderType.LIMIT, now=datetime.now(UTC))
    assert order.status is PaperOrderStatus.PENDING
    assert broker.process_candle(candle("8.5", "10.5"))[0].status is PaperOrderStatus.STOPPED


def test_oco_prioriza_stop_quando_stop_e_alvo_ocorrem_no_mesmo_candle() -> None:
    broker = PaperBroker(InMemoryPaperOrderRepository())
    order = broker.register(ticket(), PaperOrderType.LIMIT, now=datetime.now(UTC))
    processed = broker.process_candle(candle("8", "13"))[0]
    assert processed.id == order.id
    assert processed.status is PaperOrderStatus.STOPPED


def test_mercado_sem_book_e_bloqueado() -> None:
    broker = PaperBroker(InMemoryPaperOrderRepository())
    with pytest.raises(ValueError, match="bid/ask"):
        broker.register(ticket(), PaperOrderType.MARKET, now=datetime.now(UTC))


def test_mercado_usa_ask_real_para_compra() -> None:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    quote = Quote(
        symbol="PETR4",
        price=Decimal("10.05"),
        timestamp=now,
        source="test",
        bid=Decimal("10"),
        ask=Decimal("10.10"),
    )
    order = PaperBroker(InMemoryPaperOrderRepository()).register(
        ticket(), PaperOrderType.MARKET, quote=quote, now=now
    )
    assert order.fill_price == Decimal("10.10")
    assert order.status is PaperOrderStatus.OPEN
