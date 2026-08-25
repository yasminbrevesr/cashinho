"""Diário automático de decisões e operações PAPER."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.chrome import page_header, sidebar
from app.components.journal import decision_rows, paper_trade_rows
from app.runtime import journal_session_factory
from cashinho.adapters.persistence.repositories import JournalRepository
from cashinho.config.settings import get_settings

settings = get_settings()
sidebar(settings)
page_header("Diário", "Histórico auditável de FinalDecision e ordens PAPER")

with journal_session_factory()() as session:
    repository = JournalRepository(session)
    decisions = repository.list_recent_decisions(limit=200)
    trades = repository.list_recent_paper_trades(limit=200)
    legacy = repository.list_recent(limit=100)

decision_tab, trade_tab, legacy_tab = st.tabs(
    ["Decisões", "Operações PAPER", "Registros legados"]
)
with decision_tab:
    if decisions:
        st.dataframe(decision_rows(decisions), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma FinalDecision registrada.", icon="📒")
with trade_tab:
    if trades:
        st.dataframe(paper_trade_rows(trades), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma ordem PAPER auditada.", icon="📒")
with legacy_tab:
    if not legacy:
        st.caption("Nenhum registro no formato anterior.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": entry.timestamp,
                        "Ativo": entry.symbol,
                        "Modo": entry.mode.value,
                        "Estado": entry.state.value,
                        "Score": entry.score,
                        "Resultado": entry.result,
                    }
                    for entry in legacy
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

st.caption(f"Banco: `{settings.database_url}`")
