"""Modelos do portao de qualidade de dados.

Qualidade de dados e modulo de primeira classe, nao auxiliar. Se os dados
necessarios estiverem ausentes, atrasados ou inconsistentes, o resultado e
ANALISE BLOQUEADA e o pipeline para.
"""

from __future__ import annotations

from pydantic import Field

from cashinho.domain.enums import DataStatus, Severity
from cashinho.domain.types import DomainModel, UtcDatetime


class DataQualityIssue(DomainModel):
    """Um problema identificado nos dados.

    `evidence` guarda o dado concreto que sustenta o problema, e nao uma
    descricao gerada. Sem isso o relatorio nao e auditavel.
    """

    code: str = Field(description="Codigo estavel, ex.: GAP, STALE, DUPLICATE")
    severity: Severity
    message: str
    evidence: str = ""

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


class DataQualityReport(DomainModel):
    """Resultado consolidado da verificacao de qualidade.

    O status e derivado da lista de problemas, nunca informado a mao:
    qualquer CRITICAL bloqueia; qualquer WARNING degrada.
    """

    symbol: str
    source: str
    status: DataStatus
    issues: tuple[DataQualityIssue, ...] = ()
    checked_at: UtcDatetime
    latency_ms: int | None = Field(default=None, ge=0)
    candles_evaluated: int = Field(default=0, ge=0)

    @classmethod
    def from_issues(
        cls,
        *,
        symbol: str,
        source: str,
        issues: tuple[DataQualityIssue, ...],
        checked_at: UtcDatetime,
        latency_ms: int | None = None,
        candles_evaluated: int = 0,
    ) -> DataQualityReport:
        """Constroi o relatorio derivando o status dos problemas."""
        if any(i.severity is Severity.CRITICAL for i in issues):
            status = DataStatus.BLOCKED
        elif any(i.severity is Severity.WARNING for i in issues):
            status = DataStatus.DEGRADED
        else:
            status = DataStatus.OK
        return cls(
            symbol=symbol,
            source=source,
            status=status,
            issues=issues,
            checked_at=checked_at,
            latency_ms=latency_ms,
            candles_evaluated=candles_evaluated,
        )

    @property
    def blocked(self) -> bool:
        return self.status is DataStatus.BLOCKED

    @property
    def critical_issues(self) -> tuple[DataQualityIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.CRITICAL)

    def summary(self) -> str:
        if not self.issues:
            return f"{self.symbol}: dados sem problemas identificados"
        return f"{self.symbol}: {len(self.issues)} problema(s) — status {self.status}"
