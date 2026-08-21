"""Risk Manager — limites vigentes."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar
from cashinho.config.settings import get_settings

settings = get_settings()
profile = settings.risk_profile()
sidebar(settings)
page_header(
    "Risk Manager",
    "O Risk Manager tem autoridade superior a estrategia. Uma rejeicao de risco nao pode ser sobrescrita.",
)

if profile.kill_switch_active:
    st.error("KILL SWITCH ATIVO — nenhuma nova operacao sera aprovada.", icon="⛔")
else:
    st.success("Kill switch inativo.", icon="✅")

st.subheader("Limites vigentes")
col1, col2, col3 = st.columns(3)
col1.metric("Capital", f"R$ {profile.capital:,.2f}")
col1.metric("Risco por operacao", f"{profile.risk_per_trade_pct}%")
col1.metric("Risco monetario por operacao", f"R$ {profile.monetary_risk_per_trade:,.2f}")

col2.metric("Perda diaria maxima", f"{profile.max_daily_loss_pct}%")
col2.metric("Drawdown maximo", f"{profile.max_drawdown_pct}%")
col2.metric("R:R minimo", f"{profile.min_risk_reward}")

col3.metric("Trades por dia", profile.max_trades_per_day)
col3.metric("Perdas consecutivas", profile.max_consecutive_losses)
col3.metric("Posicoes abertas", profile.max_open_positions)

st.divider()
placeholder(
    "Fase 4",
    [
        "Avaliacao das regras contra o estado real do dia",
        "Consumo acumulado de perda diaria, exposicao e numero de operacoes",
        "Dimensionamento de posicao derivado do risco, com a restricao limitante nomeada",
        "Acionamento manual e automatico do kill switch",
    ],
    nota="Os valores acima vem da configuracao, ainda nao do estado operacional.",
)
