"""Dashboard — visao geral do estado do sistema."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar
from app.components.feed import render_feed_status
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import IMPLEMENTED_MODES, get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.domain.enums import Timeframe

MONITORED_SYMBOL = "PETR4"
"""Ativo monitorado nesta fase - o scanner completo da B3 e outra etapa."""

settings = get_settings()
clock = SystemClock()
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

st.subheader("Fonte de dados")
choice = build_market_data_provider(settings, clock)
capabilities = choice.provider.capabilities

col1, col2, col3 = st.columns(3)
col1.metric("Provider", capabilities.name)
col2.metric(
    "Tempo real",
    "SIM" if capabilities.supports_realtime else "NAO",
    help=(
        "Por D9, fonte sem tempo real nao habilita PAPER, ASSISTED nem LIVE."
    ),
)
col3.metric(
    "Modo compativel",
    "SIM" if capabilities.allows_mode(settings.mode) else "NAO",
    help=capabilities.rejection_reason(settings.mode, Timeframe.M1) or "",
)

motivo = capabilities.rejection_reason(settings.mode, Timeframe.M1)
if motivo:
    st.warning(f"{motivo}.", icon="⚠️")

render_feed_status(choice, MONITORED_SYMBOL, settings.display_timezone)

st.divider()
placeholder(
    "Fase 5",
    [
        "Oportunidades ativas com estado, score e prazo de expiracao",
        "Consumo dos limites de risco do dia",
        "Resumo do diario e desempenho recente",
    ],
)
