"""Registro de execucao e diario.

`AnalysisRun` e o que torna uma analise reproduzivel: sem versao de codigo,
hash de configuracao, provider e relatorio de qualidade, nenhuma decisao
registrada pode ser reconstruida depois.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from cashinho.domain.enums import Mode, OpportunityState
from cashinho.domain.quality import DataQualityReport
from cashinho.domain.types import DomainModel, Money, Price, UtcDatetime


class AnalysisRun(DomainModel):
    """Contexto auditavel de uma execucao de analise."""

    id: UUID = Field(default_factory=uuid4)
    mode: Mode
    started_at: UtcDatetime
    clock_kind: str = Field(description="SystemClock | FrozenClock | ReplayClock")
    code_version: str
    config_hash: str
    provider: str
    symbol: str | None = None
    data_quality: DataQualityReport | None = None
    notes: str = ""


class JournalEntry(DomainModel):
    """Registro de uma oportunidade ou operacao no diario.

    Campos de saida ficam opcionais porque a entrada nasce no momento da
    decisao e so e completada quando a posicao encerra.
    """

    id: UUID = Field(default_factory=uuid4)
    analysis_run_id: UUID | None = None

    symbol: str
    timestamp: UtcDatetime
    mode: Mode
    state: OpportunityState

    setup_name: str = ""
    timeframes: str = Field(default="", description="Ex.: 60m/15m/5m/1m")
    score: int | None = Field(default=None, ge=0, le=100)

    entry: Price | None = None
    stop: Price | None = None
    target: Price | None = None
    quantity: int | None = Field(default=None, ge=0)

    exit_price: Price | None = None
    exit_at: UtcDatetime | None = None
    result: Money | None = None

    risk_amount: Money | None = None
    risk_reward: str | None = None

    entry_reason: str = ""
    exit_reason: str = ""
    context: str = ""


class DecisionJournalRecord(DomainModel):
    """Snapshot idempotente de uma decisão final produzida pelo pipeline."""

    idempotency_key: str
    timestamp: UtcDatetime
    symbol: str
    should_enter: bool
    side: str
    timeframe: str | None = None
    confidence: int = Field(ge=0, le=100)
    primary_reason: str
    reasons: tuple[str, ...] = ()
    entry: Price | None = None
    stop: Price | None = None
    target: Price | None = None
    risk_reward: Decimal | None = None
    mode: Mode


class PaperTradeJournalRecord(DomainModel):
    """Espelho auditável do último estado conhecido de uma ordem PAPER."""

    paper_order_id: str
    decision_key: str | None = None
    symbol: str
    side: str
    timeframe: str | None = None
    order_type: str
    quantity: int = Field(gt=0)
    entry: Price
    stop: Price
    target: Price
    status: str
    created_at: UtcDatetime
    filled_at: UtcDatetime | None = None
    fill_price: Price | None = None
    closed_at: UtcDatetime | None = None
    close_price: Price | None = None
    close_reason: str | None = None
    monetary_risk: Money
    notional: Money
    pnl_value: Money | None = None
    pnl_pct: Decimal | None = None
    result_in_r: Decimal | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class PositionDecisionJournalRecord(DomainModel):
    """Mudança relevante de estado decidida para uma posição PAPER aberta."""

    idempotency_key: str
    paper_order_id: str
    timestamp: UtcDatetime
    symbol: str
    side: str
    action: str
    confidence: int = Field(ge=0, le=100)
    current_price: Price | None = None
    stop: Price
    target: Price
    exit_price: Price | None = None
    exit_reason: str | None = None
    primary_reason: str
    reasons: tuple[str, ...] = ()


class PaperOrderEventRecord(DomainModel):
    """Transição imutável de uma ordem/posição PAPER."""

    idempotency_key: str
    paper_order_id: str
    timestamp: UtcDatetime
    symbol: str
    side: str
    status: str
    quantity: int = Field(gt=0)
    fill_price: Price | None = None
    close_price: Price | None = None
    close_reason: str | None = None
    pnl_value: Money | None = None
    result_in_r: Decimal | None = None
