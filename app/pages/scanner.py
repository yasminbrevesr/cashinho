"""Scanner B3 — varredura de ativos liquidos."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar

sidebar()
page_header("Scanner B3", "Varredura de ativos liquidos e priorizacao de candidatos")

st.warning(
    "O scanner depende de um provedor de dados com historico intradiario confiavel. "
    "Ate la, qualquer lista exibida aqui seria inventada.",
    icon="⚠️",
)

placeholder(
    "Fase pos-7",
    [
        "Universo de ativos filtrado por liquidez e volume financeiro medio",
        "Aplicacao do portao de qualidade de dados por ativo antes da analise",
        "Ordenacao por score explicavel, nunca por retorno historico isolado",
        "Exclusao explicita de ativos bloqueados, com o motivo visivel",
    ],
    nota="Depende das Fases 2 (dados), 3 (indicadores) e 5 (scoring).",
)
