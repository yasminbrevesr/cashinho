"""Conversao entre modelos de dominio e linhas de banco.

Ponto unico de traducao. Se algum dia o schema divergir do dominio, a
divergencia fica visivel aqui em vez de se espalhar pelo codigo.
"""

from __future__ import annotations

import json
from uuid import UUID

from cashinho.adapters.persistence.models import (
    AnalysisRunRow,
    DecisionJournalRow,
    JournalEntryRow,
    PaperOrderEventRow,
    PaperTradeJournalRow,
    PositionDecisionJournalRow,
)
from cashinho.domain.enums import Mode, OpportunityState
from cashinho.domain.journal import (
    AnalysisRun,
    DecisionJournalRecord,
    JournalEntry,
    PaperOrderEventRecord,
    PaperTradeJournalRecord,
    PositionDecisionJournalRecord,
)


def analysis_run_to_row(run: AnalysisRun) -> AnalysisRunRow:
    quality = run.data_quality
    return AnalysisRunRow(
        id=str(run.id),
        mode=run.mode.value,
        started_at=run.started_at,
        clock_kind=run.clock_kind,
        code_version=run.code_version,
        config_hash=run.config_hash,
        provider=run.provider,
        symbol=run.symbol,
        data_quality_status=quality.status.value if quality else None,
        data_quality_json=quality.model_dump_json() if quality else None,
        notes=run.notes,
    )


def journal_entry_to_row(entry: JournalEntry) -> JournalEntryRow:
    return JournalEntryRow(
        id=str(entry.id),
        analysis_run_id=str(entry.analysis_run_id) if entry.analysis_run_id else None,
        symbol=entry.symbol,
        timestamp=entry.timestamp,
        mode=entry.mode.value,
        state=entry.state.value,
        setup_name=entry.setup_name,
        timeframes=entry.timeframes,
        score=entry.score,
        entry=entry.entry,
        stop=entry.stop,
        target=entry.target,
        quantity=entry.quantity,
        exit_price=entry.exit_price,
        exit_at=entry.exit_at,
        result=entry.result,
        risk_amount=entry.risk_amount,
        risk_reward=entry.risk_reward,
        entry_reason=entry.entry_reason,
        exit_reason=entry.exit_reason,
        context=entry.context,
    )


def row_to_journal_entry(row: JournalEntryRow) -> JournalEntry:
    return JournalEntry(
        id=UUID(row.id),
        analysis_run_id=UUID(row.analysis_run_id) if row.analysis_run_id else None,
        symbol=row.symbol,
        timestamp=row.timestamp,
        mode=Mode(row.mode),
        state=OpportunityState(row.state),
        setup_name=row.setup_name,
        timeframes=row.timeframes,
        score=row.score,
        entry=row.entry,
        stop=row.stop,
        target=row.target,
        quantity=row.quantity,
        exit_price=row.exit_price,
        exit_at=row.exit_at,
        result=row.result,
        risk_amount=row.risk_amount,
        risk_reward=row.risk_reward,
        entry_reason=row.entry_reason,
        exit_reason=row.exit_reason,
        context=row.context,
    )


def decision_record_to_row(record: DecisionJournalRecord) -> DecisionJournalRow:
    return DecisionJournalRow(
        idempotency_key=record.idempotency_key,
        timestamp=record.timestamp,
        symbol=record.symbol,
        should_enter=record.should_enter,
        side=record.side,
        timeframe=record.timeframe,
        confidence=record.confidence,
        primary_reason=record.primary_reason,
        reasons_json=json.dumps(record.reasons, ensure_ascii=False),
        entry=record.entry,
        stop=record.stop,
        target=record.target,
        risk_reward=record.risk_reward,
        mode=record.mode.value,
    )


def row_to_decision_record(row: DecisionJournalRow) -> DecisionJournalRecord:
    return DecisionJournalRecord(
        idempotency_key=row.idempotency_key,
        timestamp=row.timestamp,
        symbol=row.symbol,
        should_enter=row.should_enter,
        side=row.side,
        timeframe=row.timeframe,
        confidence=row.confidence,
        primary_reason=row.primary_reason,
        reasons=tuple(json.loads(row.reasons_json)),
        entry=row.entry,
        stop=row.stop,
        target=row.target,
        risk_reward=row.risk_reward,
        mode=Mode(row.mode),
    )


def paper_trade_record_to_row(record: PaperTradeJournalRecord) -> PaperTradeJournalRow:
    return PaperTradeJournalRow(**record.model_dump())


def row_to_paper_trade_record(row: PaperTradeJournalRow) -> PaperTradeJournalRecord:
    return PaperTradeJournalRecord(
        paper_order_id=row.paper_order_id,
        decision_key=row.decision_key,
        symbol=row.symbol,
        side=row.side,
        timeframe=row.timeframe,
        order_type=row.order_type,
        quantity=row.quantity,
        entry=row.entry,
        stop=row.stop,
        target=row.target,
        status=row.status,
        created_at=row.created_at,
        filled_at=row.filled_at,
        fill_price=row.fill_price,
        closed_at=row.closed_at,
        close_price=row.close_price,
        close_reason=row.close_reason,
        monetary_risk=row.monetary_risk,
        notional=row.notional,
        pnl_value=row.pnl_value,
        pnl_pct=row.pnl_pct,
        result_in_r=row.result_in_r,
        duration_seconds=row.duration_seconds,
    )


def position_decision_record_to_row(
    record: PositionDecisionJournalRecord,
) -> PositionDecisionJournalRow:
    data = record.model_dump(exclude={"reasons"})
    return PositionDecisionJournalRow(
        **data,
        reasons_json=json.dumps(record.reasons, ensure_ascii=False),
    )


def row_to_position_decision_record(
    row: PositionDecisionJournalRow,
) -> PositionDecisionJournalRecord:
    return PositionDecisionJournalRecord(
        idempotency_key=row.idempotency_key,
        paper_order_id=row.paper_order_id,
        timestamp=row.timestamp,
        symbol=row.symbol,
        side=row.side,
        action=row.action,
        confidence=row.confidence,
        current_price=row.current_price,
        stop=row.stop,
        target=row.target,
        exit_price=row.exit_price,
        exit_reason=row.exit_reason,
        primary_reason=row.primary_reason,
        reasons=tuple(json.loads(row.reasons_json)),
    )


def paper_order_event_to_row(record: PaperOrderEventRecord) -> PaperOrderEventRow:
    return PaperOrderEventRow(**record.model_dump())


def row_to_paper_order_event(row: PaperOrderEventRow) -> PaperOrderEventRecord:
    return PaperOrderEventRecord(
        idempotency_key=row.idempotency_key,
        paper_order_id=row.paper_order_id,
        timestamp=row.timestamp,
        symbol=row.symbol,
        side=row.side,
        status=row.status,
        quantity=row.quantity,
        fill_price=row.fill_price,
        close_price=row.close_price,
        close_reason=row.close_reason,
        pnl_value=row.pnl_value,
        result_in_r=row.result_in_r,
    )
