"""Registro de execucao e diario.

`AnalysisRun` e o que torna uma analise reproduzivel: sem versao de codigo,
hash de configuracao, provider e relatorio de qualidade, nenhuma decisao
registrada pode ser reconstruida depois.
"""

from __future__ import annotations

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
