"""Diario de operacoes."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.chrome import page_header, sidebar
from cashinho.adapters.persistence.repositories import JournalRepository
from cashinho.adapters.persistence.session import (
    build_session_factory,
    create_db_engine,
    init_db,
)
from cashinho.config.settings import get_settings

settings = get_settings()
sidebar(settings)
page_header("Diário", "Registro auditavel de oportunidades e operacoes")


@st.cache_resource
def _session_factory():
    engine = create_db_engine(settings)
    init_db(engine)
    return build_session_factory(engine)


factory = _session_factory()
with factory() as session:
    entries = JournalRepository(session).list_recent(limit=100)

if not entries:
    st.info(
        "Diario vazio. Os registros passam a ser gravados automaticamente quando "
        "o pipeline de analise entrar em operacao (Fase 5).",
        icon="📒",
    )
else:
    frame = pd.DataFrame(
        [
            {
                "Data": e.timestamp.astimezone().strftime("%d/%m/%Y %H:%M"),
                "Ativo": e.symbol,
                "Modo": e.mode.value,
                "Estado": e.state.value,
                "Setup": e.setup_name,
                "Score": e.score,
                "Entrada": e.entry,
                "Stop": e.stop,
                "Alvo": e.target,
                "Qtd": e.quantity,
                "Resultado": e.result,
            }
            for e in entries
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)

st.caption(f"Banco: `{settings.database_url}`")
