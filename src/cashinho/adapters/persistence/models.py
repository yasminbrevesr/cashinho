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

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
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


class DecisionJournalRow(Base):
    """Decisão binária auditada com chave natural de idempotência."""

    __tablename__ = "decision_journal"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    should_enter: Mapped[bool] = mapped_column(Boolean, index=True)
    side: Mapped[str] = mapped_column(String(8))
    timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer)
    primary_reason: Mapped[str] = mapped_column(Text)
    reasons_json: Mapped[str] = mapped_column(Text)
    entry: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    stop: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    target: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    risk_reward: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)


class PaperTradeJournalRow(Base):
    """Último estado auditado de cada ordem PAPER."""

    __tablename__ = "paper_trade_journal"

    paper_order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    entry: Mapped[Decimal] = mapped_column(DecimalText)
    stop: Mapped[Decimal] = mapped_column(DecimalText)
    target: Mapped[Decimal] = mapped_column(DecimalText)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    fill_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    monetary_risk: Mapped[Decimal] = mapped_column(DecimalText)
    notional: Mapped[Decimal] = mapped_column(DecimalText)
    pnl_value: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    pnl_pct: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    result_in_r: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PositionDecisionJournalRow(Base):
    """Eventos HOLD/EXIT relevantes, idempotentes por posição e candle."""

    __tablename__ = "position_decision_journal"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    paper_order_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    action: Mapped[str] = mapped_column(String(8), index=True)
    confidence: Mapped[int] = mapped_column(Integer)
    current_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    stop: Mapped[Decimal] = mapped_column(DecimalText)
    target: Mapped[Decimal] = mapped_column(DecimalText)
    exit_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_reason: Mapped[str] = mapped_column(Text)
    reasons_json: Mapped[str] = mapped_column(Text)


class PaperOrderEventRow(Base):
    """Histórico imutável das transições relevantes do Paper Broker."""

    __tablename__ = "paper_order_events"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    paper_order_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    fill_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pnl_value: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    result_in_r: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)


Index(
    "ix_decision_journal_symbol_timestamp",
    DecisionJournalRow.symbol,
    DecisionJournalRow.timestamp,
)
