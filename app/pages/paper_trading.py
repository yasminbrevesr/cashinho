"""Paper Trading."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar

sidebar()
page_header("Paper Trading", "Simulacao de ordens sem envio ao mercado")

st.info("Nenhuma ordem real e enviada por esta aplicacao.", icon="🔒")

placeholder(
    "Fase pos-7",
    [
        "Paper Broker: place_order, cancel_order, get_orders, get_positions, get_balance",
        "Simulacao progressiva de stop, alvo, OCO, spread e slippage",
        "Posicoes abertas e resultado acumulado do dia",
        "Registro automatico de cada operacao no diario",
    ],
)
