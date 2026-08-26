"""Integração auditável entre FinalDecision, Paper Broker e SQLite."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from cashinho.adapters.persistence.repositories import JournalRepository
from cashinho.adapters.persistence.session import session_scope
from cashinho.domain.enums import Mode
from cashinho.domain.journal import (
    DecisionJournalRecord,
    PaperOrderEventRecord,
    PaperTradeJournalRecord,
    PositionDecisionJournalRecord,
)
from cashinho.pipeline.final_decision import FinalDecision
from cashinho.pipeline.paper_broker import PaperOrder, PaperOrderObserver
from cashinho.pipeline.paper_performance import realized_pnl
from cashinho.pipeline.position_manager import PositionDecision


def decision_idempotency_key(decision: FinalDecision) -> str:
    timeframe = decision.timeframe.value if decision.timeframe else "NONE"
    state = "ENTER" if decision.should_enter else "REJECT"
    identity = f"{decision.symbol}|{timeframe}|{decision.timestamp.isoformat()}|{state}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def decision_record(decision: FinalDecision, mode: Mode) -> DecisionJournalRecord:
    return DecisionJournalRecord(
        idempotency_key=decision_idempotency_key(decision),
        timestamp=decision.timestamp,
        symbol=decision.symbol,
        should_enter=decision.should_enter,
        side=decision.side,
        timeframe=decision.timeframe.value if decision.timeframe else None,
        confidence=decision.confidence,
        primary_reason=decision.primary_reason,
        reasons=decision.reasons,
        entry=decision.entry,
        stop=decision.stop,
        target=decision.target,
        risk_reward=(Decimal(str(decision.risk_reward)) if decision.risk_reward else None),
        mode=mode,
    )


def paper_trade_record(order: PaperOrder) -> PaperTradeJournalRecord:
    result = realized_pnl(order)
    duration_seconds = (
        int(result.duration.total_seconds())
        if result is not None and result.duration is not None
        else None
    )
    return PaperTradeJournalRecord(
        paper_order_id=order.id,
        decision_key=order.decision_key,
        symbol=order.ticket.symbol,
        side=order.ticket.side,
        timeframe=order.ticket.timeframe,
        order_type=order.order_type.value,
        quantity=order.ticket.quantity,
        entry=order.ticket.entry,
        stop=order.ticket.stop,
        target=order.ticket.target,
        status=order.status.value,
        created_at=order.created_at,
        filled_at=order.filled_at,
        fill_price=order.fill_price,
        closed_at=order.closed_at,
        close_price=order.close_price,
        close_reason=order.close_reason,
        monetary_risk=order.ticket.monetary_risk,
        notional=order.ticket.notional,
        pnl_value=result.pnl_value if result else None,
        pnl_pct=result.pnl_pct if result else None,
        result_in_r=result.result_in_r if result else None,
        duration_seconds=duration_seconds,
    )


def position_decision_idempotency_key(
    order_id: str, decision: PositionDecision
) -> str:
    reason = decision.exit_reason.value if decision.exit_reason else "NONE"
    identity = (
        f"{order_id}|{decision.timestamp.isoformat()}|{decision.action.value}|{reason}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def paper_order_event_record(order: PaperOrder) -> PaperOrderEventRecord:
    result = realized_pnl(order)
    timestamp = order.closed_at or order.filled_at or order.created_at
    identity = f"{order.id}|{order.status.value}|{timestamp.isoformat()}"
    return PaperOrderEventRecord(
        idempotency_key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        paper_order_id=order.id,
        timestamp=timestamp,
        symbol=order.ticket.symbol,
        side=order.ticket.side,
        status=order.status.value,
        quantity=order.ticket.quantity,
        fill_price=order.fill_price,
        close_price=order.close_price,
        close_reason=order.close_reason,
        pnl_value=result.pnl_value if result else None,
        result_in_r=result.result_in_r if result else None,
    )


def position_decision_record(
    order_id: str, decision: PositionDecision
) -> PositionDecisionJournalRecord:
    return PositionDecisionJournalRecord(
        idempotency_key=position_decision_idempotency_key(order_id, decision),
        paper_order_id=order_id,
        timestamp=decision.timestamp,
        symbol=decision.symbol,
        side=decision.side,
        action=decision.action.value,
        confidence=decision.confidence,
        current_price=decision.current_price,
        stop=decision.stop,
        target=decision.target,
        exit_price=decision.exit_price,
        exit_reason=decision.exit_reason.value if decision.exit_reason else None,
        primary_reason=decision.primary_reason,
        reasons=decision.reasons,
    )


class JournalAuditService(PaperOrderObserver):
    """Observador transacional usado pelos fluxos PAPER e de análise."""

    def __init__(self, factory: sessionmaker[Session], mode: Mode = Mode.PAPER) -> None:
        self._factory = factory
        self._mode = mode

    def record_decision(self, decision: FinalDecision, *, mode: Mode | None = None) -> bool:
        with session_scope(self._factory) as session:
            return JournalRepository(session).record_decision(
                decision_record(decision, mode or self._mode)
            )

    def on_order_changed(self, order: PaperOrder) -> None:
        with session_scope(self._factory) as session:
            repository = JournalRepository(session)
            repository.upsert_paper_trade(paper_trade_record(order))
            repository.record_paper_order_event(paper_order_event_record(order))

    def record_position_decision(
        self, order_id: str, decision: PositionDecision
    ) -> bool:
        with session_scope(self._factory) as session:
            return JournalRepository(session).record_position_decision(
                position_decision_record(order_id, decision)
            )

    def sync_orders(self, orders: Iterable[PaperOrder]) -> None:
        """Preenche auditoria de ordens antigas; reruns não duplicam registros."""
        with session_scope(self._factory) as session:
            repository = JournalRepository(session)
            for order in orders:
                repository.upsert_paper_trade(paper_trade_record(order))
                repository.record_paper_order_event(paper_order_event_record(order))
