"""Repositorios.

Interface estreita e deliberada: a UI e o pipeline nao montam consultas.
Isso mantem o SQLAlchemy contido no adaptador e permite trocar o backend
de persistencia sem tocar no restante.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cashinho.adapters.persistence.mappers import (
    analysis_run_to_row,
    decision_record_to_row,
    journal_entry_to_row,
    paper_order_event_to_row,
    paper_trade_record_to_row,
    position_decision_record_to_row,
    row_to_decision_record,
    row_to_journal_entry,
    row_to_paper_order_event,
    row_to_paper_trade_record,
    row_to_position_decision_record,
)
from cashinho.adapters.persistence.models import (
    AnalysisRunRow,
    DecisionJournalRow,
    JournalEntryRow,
    PaperOrderEventRow,
    PaperTradeJournalRow,
    PositionDecisionJournalRow,
)
from cashinho.domain.journal import (
    AnalysisRun,
    DecisionJournalRecord,
    JournalEntry,
    PaperOrderEventRecord,
    PaperTradeJournalRecord,
    PositionDecisionJournalRecord,
)


class JournalRepository:
    """Leitura e escrita do diario."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: JournalEntry) -> None:
        self._session.add(journal_entry_to_row(entry))

    def list_recent(self, limit: int = 50) -> list[JournalEntry]:
        stmt = (
            select(JournalEntryRow)
            .order_by(JournalEntryRow.timestamp.desc())
            .limit(limit)
        )
        return [row_to_journal_entry(row) for row in self._session.scalars(stmt)]

    def list_by_symbol(self, symbol: str, limit: int = 50) -> list[JournalEntry]:
        stmt = (
            select(JournalEntryRow)
            .where(JournalEntryRow.symbol == symbol.upper())
            .order_by(JournalEntryRow.timestamp.desc())
            .limit(limit)
        )
        return [row_to_journal_entry(row) for row in self._session.scalars(stmt)]

    def count(self) -> int:
        return len(list(self._session.scalars(select(JournalEntryRow.id))))

    def record_decision(self, record: DecisionJournalRecord) -> bool:
        """Insere uma decisão apenas uma vez; retorna se houve escrita."""
        if self._session.get(DecisionJournalRow, record.idempotency_key) is not None:
            return False
        self._session.add(decision_record_to_row(record))
        return True

    def list_recent_decisions(self, limit: int = 50) -> list[DecisionJournalRecord]:
        stmt = (
            select(DecisionJournalRow)
            .order_by(DecisionJournalRow.timestamp.desc())
            .limit(limit)
        )
        return [row_to_decision_record(row) for row in self._session.scalars(stmt)]

    def count_released_decisions(self, *, start: datetime, end: datetime) -> int:
        stmt = select(func.count()).select_from(DecisionJournalRow).where(
            DecisionJournalRow.should_enter.is_(True),
            DecisionJournalRow.timestamp >= start,
            DecisionJournalRow.timestamp < end,
        )
        return int(self._session.scalar(stmt) or 0)

    def upsert_paper_trade(self, record: PaperTradeJournalRecord) -> bool:
        """Persiste a última transição da ordem de forma idempotente."""
        current = self._session.get(PaperTradeJournalRow, record.paper_order_id)
        if current is not None and row_to_paper_trade_record(current) == record:
            return False
        self._session.merge(paper_trade_record_to_row(record))
        return True

    def list_recent_paper_trades(self, limit: int = 50) -> list[PaperTradeJournalRecord]:
        stmt = (
            select(PaperTradeJournalRow)
            .order_by(PaperTradeJournalRow.created_at.desc())
            .limit(limit)
        )
        return [row_to_paper_trade_record(row) for row in self._session.scalars(stmt)]

    def record_position_decision(self, record: PositionDecisionJournalRecord) -> bool:
        """Registra apenas uma mudança relevante; HOLD repetido não polui o diário."""

        if self._session.get(PositionDecisionJournalRow, record.idempotency_key) is not None:
            return False
        latest_stmt = (
            select(PositionDecisionJournalRow)
            .where(PositionDecisionJournalRow.paper_order_id == record.paper_order_id)
            .order_by(PositionDecisionJournalRow.timestamp.desc())
            .limit(1)
        )
        latest = self._session.scalar(latest_stmt)
        if (
            latest is not None
            and latest.action == record.action
            and latest.exit_reason == record.exit_reason
            and latest.primary_reason == record.primary_reason
        ):
            return False
        self._session.add(position_decision_record_to_row(record))
        return True

    def list_recent_position_decisions(
        self, limit: int = 50
    ) -> list[PositionDecisionJournalRecord]:
        stmt = (
            select(PositionDecisionJournalRow)
            .order_by(PositionDecisionJournalRow.timestamp.desc())
            .limit(limit)
        )
        return [
            row_to_position_decision_record(row) for row in self._session.scalars(stmt)
        ]

    def record_paper_order_event(self, record: PaperOrderEventRecord) -> bool:
        if self._session.get(PaperOrderEventRow, record.idempotency_key) is not None:
            return False
        self._session.add(paper_order_event_to_row(record))
        return True

    def list_recent_paper_order_events(
        self, limit: int = 50
    ) -> list[PaperOrderEventRecord]:
        stmt = (
            select(PaperOrderEventRow)
            .order_by(PaperOrderEventRow.timestamp.desc())
            .limit(limit)
        )
        return [row_to_paper_order_event(row) for row in self._session.scalars(stmt)]


class AnalysisRunRepository:
    """Registro das execucoes de analise."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: AnalysisRun) -> None:
        self._session.add(analysis_run_to_row(run))

    def count(self) -> int:
        return len(list(self._session.scalars(select(AnalysisRunRow.id))))
