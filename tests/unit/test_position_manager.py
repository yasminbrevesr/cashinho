from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cashinho.domain.enums import Timeframe
from cashinho.domain.market import Candle, CandleSeries
from cashinho.pipeline.entry_signal import EntrySignal
from cashinho.pipeline.multi_timeframe import TimeframeAdvice
from cashinho.pipeline.paper_broker import (
    InMemoryPaperOrderRepository,
    PaperBroker,
    PaperOrder,
    PaperOrderStatus,
    PaperOrderType,
)
from cashinho.pipeline.paper_ticket import build_paper_ticket
from cashinho.pipeline.position_manager import (
    PositionAction,
    PositionExitReason,
    PositionManager,
    PositionRiskState,
    apply_position_decision,
)

START = datetime(2026, 8, 20, 12, tzinfo=UTC)


def position(side: str = "BUY") -> PaperOrder:
    stop, target = (("9", "12") if side == "BUY" else ("11", "8"))
    ticket = build_paper_ticket(
        symbol="PETR4",
        side=side,
        entry=Decimal("10"),
        stop=Decimal(stop),
        target=Decimal(target),
        quantity=10,
        timeframe="5m",
    )
    return PaperOrder(
        id="order-1",
        ticket=ticket,
        order_type=PaperOrderType.LIMIT,
        status=PaperOrderStatus.OPEN,
        created_at=START - timedelta(minutes=10),
        filled_at=START,
        fill_price=Decimal("10"),
    )


def candle(
    index: int,
    *,
    open_price: str,
    high: str,
    low: str,
    close: str,
    is_closed: bool = True,
) -> Candle:
    opened = START + timedelta(minutes=5 * index)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=5),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1000,
        is_closed=is_closed,
    )


def series(*candles: Candle) -> CandleSeries:
    return CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=candles,
        source="test",
        fetched_at=START + timedelta(hours=1),
    )


def advice(side: str, score: int = 80, *, strong: bool = True) -> TimeframeAdvice:
    return TimeframeAdvice(
        recommended_timeframe=Timeframe.M5 if strong else None,
        context_timeframes=(Timeframe.H1,),
        trigger_timeframe=Timeframe.M1,
        score=score,
        side=side,
        reasons=("teste",),
        rejection_reason=None if strong else "conflito pequeno",
    )


def signal(side: str, score: int, *, confirmed: bool) -> EntrySignal:
    return EntrySignal(
        side=side,
        status="ENTRADA LIBERADA" if confirmed else "AGUARDANDO GATILHO",
        score=score,
        entry=Decimal("10") if confirmed else None,
        stop=Decimal("9") if confirmed else None,
        target=Decimal("12") if confirmed else None,
        risk_reward=2.0 if confirmed else None,
        reasons=("teste",),
        trigger_confirmed=confirmed,
    )


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_posicao_saudavel_mantem(side: str) -> None:
    healthy = (
        series(
            candle(0, open_price="10", high="10.5", low="9.7", close="10.2"),
            candle(1, open_price="10.2", high="10.6", low="9.8", close="10.3"),
        )
        if side == "BUY"
        else series(
            candle(0, open_price="10", high="10.3", low="9.5", close="9.8"),
            candle(1, open_price="9.8", high="10.2", low="9.4", close="9.7"),
        )
    )
    decision = PositionManager().evaluate(
        position(side),
        recent_candles=healthy,
        technical_signal=None,
        timeframe_advice=advice(side),
    )
    assert decision.action is PositionAction.HOLD
    assert decision.exit_price is None


@pytest.mark.parametrize(
    ("side", "high", "low", "reason", "price"),
    [
        ("BUY", "10.5", "8.9", PositionExitReason.STOP, Decimal("9")),
        ("SELL", "11.1", "9.5", PositionExitReason.STOP, Decimal("11")),
        ("BUY", "12.1", "9.5", PositionExitReason.TARGET, Decimal("12")),
        ("SELL", "10.5", "7.9", PositionExitReason.TARGET, Decimal("8")),
    ],
)
def test_stop_e_target_encerram(
    side: str,
    high: str,
    low: str,
    reason: PositionExitReason,
    price: Decimal,
) -> None:
    decision = PositionManager().evaluate(
        position(side),
        recent_candles=series(
            candle(1, open_price="10", high=high, low=low, close="10")
        ),
        technical_signal=None,
        timeframe_advice=advice(side),
    )
    assert decision.action is PositionAction.EXIT
    assert decision.exit_reason is reason
    assert decision.exit_price == price


def test_stop_e_target_no_mesmo_candle_prioriza_stop() -> None:
    decision = PositionManager().evaluate(
        position(),
        recent_candles=series(
            candle(1, open_price="10", high="13", low="8", close="10")
        ),
        technical_signal=None,
        timeframe_advice=advice("BUY"),
    )
    assert decision.exit_reason is PositionExitReason.STOP


@pytest.mark.parametrize(
    ("side", "candles"),
    [
        (
            "BUY",
            (
                candle(1, open_price="10.3", high="10.8", low="9.8", close="10.2"),
                candle(2, open_price="10.1", high="10.5", low="9.5", close="9.8"),
                candle(3, open_price="9.8", high="10.2", low="9.2", close="9.6"),
            ),
        ),
        (
            "SELL",
            (
                candle(1, open_price="9.7", high="10.2", low="9.2", close="9.8"),
                candle(2, open_price="9.9", high="10.5", low="9.5", close="10.2"),
                candle(3, open_price="10.2", high="10.8", low="9.8", close="10.4"),
            ),
        ),
    ],
)
def test_estrutura_invalidada_exige_confirmacao(side: str, candles: tuple[Candle, ...]) -> None:
    decision = PositionManager().evaluate(
        position(side),
        recent_candles=series(*candles),
        technical_signal=None,
        timeframe_advice=advice(side),
        market_exit_price=Decimal("9.55") if side == "BUY" else Decimal("10.45"),
    )
    assert decision.action is PositionAction.EXIT
    assert decision.exit_reason is PositionExitReason.THESIS_INVALIDATED


def test_sinal_contrario_fraco_e_conflito_pequeno_mantem() -> None:
    decision = PositionManager().evaluate(
        position(),
        recent_candles=series(
            candle(1, open_price="10", high="10.5", low="9.5", close="10.1")
        ),
        technical_signal=signal("SELL", 70, confirmed=False),
        timeframe_advice=advice("SELL", 55, strong=False),
    )
    assert decision.action is PositionAction.HOLD


def test_sinal_contrario_forte_e_confirmado_sai_sem_reverter() -> None:
    decision = PositionManager().evaluate(
        position(),
        recent_candles=series(
            candle(1, open_price="10", high="10.5", low="9.5", close="10.1")
        ),
        technical_signal=signal("SELL", 82, confirmed=True),
        timeframe_advice=advice("SELL", 80),
        market_exit_price=Decimal("10.05"),
    )
    assert decision.action is PositionAction.EXIT
    assert decision.side == "BUY"
    assert decision.exit_reason is PositionExitReason.OPPOSITE_SIGNAL


def test_reversao_forte_de_contexto_sai() -> None:
    decision = PositionManager().evaluate(
        position("SELL"),
        recent_candles=series(
            candle(1, open_price="10", high="10.5", low="9.5", close="10")
        ),
        technical_signal=None,
        timeframe_advice=advice("BUY", 78),
        market_exit_price=Decimal("10.05"),
    )
    assert decision.exit_reason is PositionExitReason.CONTEXT_REVERSAL


def test_candle_aberto_e_ignorado() -> None:
    decision = PositionManager().evaluate(
        position(),
        recent_candles=series(
            candle(1, open_price="10", high="10.5", low="9.5", close="10.1"),
            candle(
                2,
                open_price="10",
                high="12.5",
                low="8.5",
                close="9",
                is_closed=False,
            ),
        ),
        technical_signal=None,
        timeframe_advice=advice("BUY"),
    )
    assert decision.action is PositionAction.HOLD


def test_saida_dinamica_sem_book_nao_fecha() -> None:
    repository = InMemoryPaperOrderRepository()
    broker = PaperBroker(repository)
    current = position()
    repository.add(current)
    decision = PositionManager().evaluate(
        current,
        recent_candles=series(
            candle(1, open_price="10", high="10.5", low="9.5", close="10")
        ),
        technical_signal=None,
        timeframe_advice=advice("BUY"),
        risk=PositionRiskState(True, "Kill switch ativo."),
        market_exit_price=None,
    )
    assert decision.action is PositionAction.EXIT
    assert not decision.can_execute
    assert apply_position_decision(broker, current, decision) is None
    assert broker.list_orders()[0].status is PaperOrderStatus.OPEN
