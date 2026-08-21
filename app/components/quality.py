"""Exibicao do relatorio de qualidade de dados.

O status aparece SEMPRE, inclusive quando OK. Mostrar apenas quando ha
problema treinaria o operador a confiar no silencio — e silencio tambem
seria o resultado de um portao que parou de rodar.
"""

from __future__ import annotations

import streamlit as st

from cashinho.domain.enums import DataStatus, Severity
from cashinho.domain.quality import DataQualityReport

_SEVERITY_ICON = {
    Severity.CRITICAL: "⛔",
    Severity.WARNING: "⚠️",
    Severity.INFO: "•",
}


def quality_panel(report: DataQualityReport, *, rejection_reason: str | None = None) -> None:
    """Renderiza o status e a evidencia de cada problema."""
    if rejection_reason is not None:
        st.error(f"**ANÁLISE BLOQUEADA** — {rejection_reason}", icon="⛔")
        return

    if report.status is DataStatus.BLOCKED:
        st.error(
            f"**ANÁLISE BLOQUEADA** — {report.symbol}: "
            f"{len(report.critical_issues)} problema(s) crítico(s) nos dados.",
            icon="⛔",
        )
    elif report.status is DataStatus.DEGRADED:
        st.warning(
            f"**DADOS DEGRADADOS** — {report.symbol}: análise permitida com ressalvas.",
            icon="⚠️",
        )
    else:
        st.success(
            f"**DADOS OK** — {report.candles_evaluated} candles verificados.", icon="✅"
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Origem", report.source)
    col2.metric("Candles", report.candles_evaluated)
    col3.metric("Verificado em", report.checked_at.strftime("%H:%M:%S UTC"))

    if not report.issues:
        return

    with st.expander(f"Problemas identificados ({len(report.issues)})", expanded=report.blocked):
        for issue in report.issues:
            icon = _SEVERITY_ICON.get(issue.severity, "•")
            st.markdown(f"{icon} **{issue.code}** — {issue.message}")
            if issue.evidence:
                st.caption(f"evidência: `{issue.evidence}`")
