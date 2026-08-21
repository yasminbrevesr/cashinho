"""Modelos de persistencia.

Decisao arquitetural D7: estas classes NAO sao os modelos de dominio.
Sao uma representacao de armazenamento, com ciclo de vida proprio.
A conversao acontece em `mappers.py`.

Motivo: o diario precisa sobreviver a refatoracoes do dominio. Se as duas
camadas fossem a mesma classe, cada mudanca de modelo exigiria migracao
imediata ou perda de historico.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cashinho.adapters.persistence.sa_types import DecimalText, UtcDateTime


class Base(DeclarativeBase):
    """Base declarativa do Cashinho."""


class AnalysisRunRow(Base):
    """Execucao de analise registrada para auditoria."""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    clock_kind: Mapped[str] = mapped_column(String(32))
    code_version: Mapped[str] = mapped_column(String(32))
    config_hash: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    data_quality_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_quality_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class JournalEntryRow(Base):
    """Registro do diario."""

    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analysis_runs.id"), nullable=True
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)

    setup_name: Mapped[str] = mapped_column(String(64), default="")
    timeframes: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    entry: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    stop: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    target: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    exit_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    exit_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    result: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)

    risk_amount: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    risk_reward: Mapped[str | None] = mapped_column(String(16), nullable=True)

    entry_reason: Mapped[str] = mapped_column(Text, default="")
    exit_reason: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")


Index("ix_journal_symbol_timestamp", JournalEntryRow.symbol, JournalEntryRow.timestamp)
