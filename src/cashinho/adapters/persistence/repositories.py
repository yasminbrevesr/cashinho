"""Repositorios.

Interface estreita e deliberada: a UI e o pipeline nao montam consultas.
Isso mantem o SQLAlchemy contido no adaptador e permite trocar o backend
de persistencia sem tocar no restante.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cashinho.adapters.persistence.mappers import (
    analysis_run_to_row,
    journal_entry_to_row,
    row_to_journal_entry,
)
from cashinho.adapters.persistence.models import AnalysisRunRow, JournalEntryRow
from cashinho.domain.journal import AnalysisRun, JournalEntry


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


class AnalysisRunRepository:
    """Registro das execucoes de analise."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: AnalysisRun) -> None:
        self._session.add(analysis_run_to_row(run))

    def count(self) -> int:
        return len(list(self._session.scalars(select(AnalysisRunRow.id))))
