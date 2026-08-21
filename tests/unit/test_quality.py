"""Portao de qualidade: derivacao do status a partir dos problemas."""

from __future__ import annotations

import pytest

from cashinho.domain.enums import DataStatus, Severity
from cashinho.domain.quality import DataQualityIssue, DataQualityReport
from tests.conftest import REFERENCE_INSTANT


def _issue(severity: Severity, code: str = "GAP") -> DataQualityIssue:
    return DataQualityIssue(code=code, severity=severity, message="teste", evidence="x")


def _report(*issues: DataQualityIssue) -> DataQualityReport:
    return DataQualityReport.from_issues(
        symbol="PETR4",
        source="fixture",
        issues=issues,
        checked_at=REFERENCE_INSTANT,
    )


def test_sem_problemas_status_ok() -> None:
    report = _report()
    assert report.status is DataStatus.OK
    assert not report.blocked


def test_warning_degrada() -> None:
    assert _report(_issue(Severity.WARNING)).status is DataStatus.DEGRADED


def test_critical_bloqueia() -> None:
    report = _report(_issue(Severity.WARNING), _issue(Severity.CRITICAL, "STALE"))
    assert report.status is DataStatus.BLOCKED
    assert report.blocked
    assert len(report.critical_issues) == 1


def test_info_nao_altera_status() -> None:
    assert _report(_issue(Severity.INFO)).status is DataStatus.OK


@pytest.mark.parametrize(
    ("severities", "esperado"),
    [
        ((Severity.INFO,), DataStatus.OK),
        ((Severity.INFO, Severity.WARNING), DataStatus.DEGRADED),
        ((Severity.CRITICAL,), DataStatus.BLOCKED),
        ((Severity.CRITICAL, Severity.INFO), DataStatus.BLOCKED),
    ],
)
def test_derivacao_do_status(severities: tuple[Severity, ...], esperado: DataStatus) -> None:
    assert _report(*[_issue(s) for s in severities]).status is esperado
