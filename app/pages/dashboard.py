"""Dashboard operacional baseado no diário e no Paper Broker."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import streamlit as st

from app.components.chrome import page_header, sidebar
from app.components.feed import render_feed_status
from app.components.journal import operational_decision_rows, paper_trade_rows
from app.components.paper_summary import money
from app.runtime import build_paper_broker, journal_session_factory
from cashinho.adapters.persistence.repositories import JournalRepository
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.domain.errors import CashinhoError
from cashinho.pipeline.paper_market import collect_paper_market
from cashinho.pipeline.paper_performance import summarize_orders

MONITORED_SYMBOL = "PETR4"

settings = get_settings()
clock = SystemClock()
sidebar(settings)
page_header("Dashboard", "Decisões auditadas e operação PAPER")

choice = build_market_data_provider(
    settings, clock, fixtures_root=settings.data_dir / "fixtures"
)
feed_status = "HISTÓRICO"
if choice.is_metatrader:
    try:
        feed_status = choice.provider.feed_status(MONITORED_SYMBOL).value  # type: ignore[attr-defined]
    except (CashinhoError, RuntimeError):
        feed_status = "OFFLINE"

profile = settings.risk_profile()
source_top = st.columns(3)
source_top[0].metric("Provider", choice.provider.capabilities.name)
source_top[1].metric(
    "Tempo real", "SIM" if choice.provider.capabilities.supports_realtime else "NÃO"
)
source_top[2].metric("Status do feed", feed_status)
account_top = st.columns(3)
account_top[0].metric("Modo", settings.mode.value)
account_top[1].metric("Capital", money(profile.capital))
account_top[2].metric("Risco por operação", f"{profile.risk_per_trade_pct}%")

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
with journal_session_factory()() as session:
    repository = JournalRepository(session)
    decisions = repository.list_recent_decisions(limit=20)
    position_decisions = repository.list_recent_position_decisions(limit=20)
    trades = repository.list_recent_paper_trades(limit=20)
    today = clock.now().date()
    day_start = datetime.combine(today, time.min, tzinfo=UTC)
    released_today = repository.count_released_decisions(
        start=day_start,
        end=day_start + timedelta(days=1),
    )

st.divider()
st.subheader("Resumo")
first = st.columns(3)
first[0].metric("Entradas liberadas hoje", released_today)
first[1].metric("Operações PAPER abertas", summary.open_positions)
first[2].metric("P&L PAPER realizado", money(summary.realized_pnl))
second = st.columns(2)
second[0].metric("P&L PAPER aberto", money(summary.unrealized_pnl))
second[1].metric("Risco em uso", money(summary.exposed_risk))
if summary.unpriced_positions:
    st.caption("P&L aberto oculto porque não há cotação válida para todas as posições.")

st.divider()
st.subheader("Últimas decisões")
if decisions or position_decisions:
    st.dataframe(
        operational_decision_rows(decisions, position_decisions)[:20],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Nenhuma decisão operacional auditada ainda.")

st.divider()
st.subheader("Últimas operações")
if trades:
    st.dataframe(paper_trade_rows(trades), use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma operação PAPER auditada ainda.")

with st.expander("Status detalhado do feed"):
    render_feed_status(choice, MONITORED_SYMBOL, settings.display_timezone)
