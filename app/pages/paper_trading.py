"""Acompanhamento operacional estritamente PAPER."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, sidebar
from app.components.feed import render_source_banner
from app.components.paper_summary import render_paper_summary
from app.components.positions import (
    render_closed_positions,
    render_open_positions,
    render_pending_orders,
)
from app.runtime import build_paper_broker
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.pipeline.paper_market import collect_paper_market
from cashinho.pipeline.paper_performance import summarize_orders

settings = get_settings()
clock = SystemClock()
sidebar(settings)
page_header("Paper Trading", "Ordens, posições e resultados simulados persistentes")

st.info(
    "Ambiente exclusivamente PAPER. Nenhuma ordem é enviada ao MetaTrader ou à corretora.",
    icon="🔒",
)

choice = build_market_data_provider(
    settings, clock, fixtures_root=settings.data_dir / "fixtures"
)
render_source_banner(choice)
broker, _audit = build_paper_broker()
orders = broker.list_orders()
market = collect_paper_market(
    choice.provider,
    orders,
    clock=clock,
    max_age_seconds=settings.mt5_stale_seconds,
)
summary = summarize_orders(
    orders,
    market_prices=market.market_prices,
    on_date=clock.now().date(),
)

st.subheader("Resumo do dia")
render_paper_summary(summary)
for error in market.errors:
    st.caption(error)

st.divider()
render_open_positions(
    broker,
    orders,
    market_prices=market.market_prices,
    close_prices=market.close_prices,
    now=clock.now(),
)
st.divider()
render_pending_orders(broker, orders)
st.divider()
render_closed_positions(orders)
