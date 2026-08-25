"""Resumo visual do portfólio PAPER."""

from __future__ import annotations

import streamlit as st

from cashinho.pipeline.paper_performance import PaperSummary


def money(value: object) -> str:
    return f"R$ {value:,.2f}" if value is not None else "—"


def render_paper_summary(summary: PaperSummary) -> None:
    first = st.columns(3)
    first[0].metric("P&L realizado", money(summary.realized_pnl))
    first[1].metric("P&L em aberto", money(summary.unrealized_pnl))
    first[2].metric("Risco atualmente exposto", money(summary.exposed_risk))
    second = st.columns(3)
    second[0].metric("Operações do dia", summary.operations)
    second[1].metric("Posições abertas", summary.open_positions)
    second[2].metric("Ordens pendentes", summary.pending_orders)
    if summary.unpriced_positions:
        st.caption(
            f"P&L aberto indisponível para {summary.unpriced_positions} posição(ões): "
            "não existe cotação válida para marcação."
        )
