"""Conversao entre modelos de dominio e linhas de banco.

Ponto unico de traducao. Se algum dia o schema divergir do dominio, a
divergencia fica visivel aqui em vez de se espalhar pelo codigo.
"""

from __future__ import annotations

from uuid import UUID

from cashinho.adapters.persistence.models import AnalysisRunRow, JournalEntryRow
from cashinho.domain.enums import Mode, OpportunityState
from cashinho.domain.journal import AnalysisRun, JournalEntry


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
