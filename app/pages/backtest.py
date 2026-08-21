"""Backtest."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar

sidebar()
page_header("Backtest", "Avaliacao historica com execucao realista")

st.warning(
    "Bom resultado historico nao indica lucratividade futura. "
    "Esta tela so sera habilitada com separacao TRAIN / VALIDATION / TEST implementada.",
    icon="⚠️",
)

placeholder(
    "Fase pos-7",
    [
        "Custos: spread, slippage, taxas e restricao de liquidez",
        "Metricas: retorno, trades, win rate, payoff, expectancy, profit factor",
        "Metricas de risco: Sharpe, Sortino, drawdown maximo, exposicao",
        "Separacao TRAIN / VALIDATION / TEST e evolucao para walk-forward",
    ],
    nota="A infraestrutura de separacao de amostras precisa existir antes da primeira estrategia.",
)
