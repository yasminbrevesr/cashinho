"""Dashboard — visao geral do estado do sistema."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar
from cashinho.config.settings import IMPLEMENTED_MODES, get_settings

settings = get_settings()
sidebar(settings)
page_header("Dashboard", "Estado atual do sistema e do capital de referencia")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Modo", settings.mode.value)
col2.metric("Capital de referencia", f"R$ {settings.capital:,.2f}")
col3.metric("Risco por operacao", f"{settings.risk_profile().risk_per_trade_pct}%")
col4.metric("Oportunidades hoje", "0")

st.divider()

st.markdown(
    "O Cashinho nao procura operacoes a qualquer custo. "
    "**NAO OPERAR** e uma decisao valida e terminal."
)
st.markdown(
    "Estados possiveis: `SETUP APROVADO` · `AGUARDANDO GATILHO` · "
    "`SETUP REJEITADO` · `NAO OPERAR` · `EXPIRADO`"
)
st.caption(f"Modos habilitados nesta versao: {', '.join(sorted(m.value for m in IMPLEMENTED_MODES))}")

st.divider()
placeholder(
    "Fase 5",
    [
        "Oportunidades ativas com estado, score e prazo de expiracao",
        "Consumo dos limites de risco do dia",
        "Resumo do diario e desempenho recente",
        "Alertas de qualidade de dados por ativo monitorado",
    ],
)
