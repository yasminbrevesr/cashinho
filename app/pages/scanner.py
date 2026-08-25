"""Ranking PAPER de oportunidades com contexto multi-timeframe."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from app.components.chrome import page_header, sidebar
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.domain.enums import DataStatus, Mode
from cashinho.pipeline.final_decision import make_final_decision
from cashinho.pipeline.indicators import IndicatorSelection
from cashinho.pipeline.market_data import load_market_data
from cashinho.pipeline.multi_timeframe import advise_timeframe, analyze_timeframes
from cashinho.pipeline.opportunities import build_opportunity
from cashinho.pipeline.paper_ticket import calculate_ticket_sizing

settings = get_settings()
sidebar(settings)
page_header("Ranking de oportunidades", "Contexto, timeframe e priorização em modo PAPER")
clock = SystemClock()
choice = build_market_data_provider(settings, clock, fixtures_root=settings.data_dir / "fixtures")
provider = choice.provider
selection = IndicatorSelection(
    ema_periods=(9, 21), vwap=True, rsi_period=14, macd=True, atr_period=14
)

st.caption(
    "Somente candles fechados participam das decisões. O ranking não envia ordens ao mercado."
)
lookback = st.number_input("Janela de análise (dias)", 5, 365, 60)

if st.button("Atualizar ranking", type="primary"):
    end = clock.now()
    start = end - timedelta(days=int(lookback))
    decisions = []
    for symbol in choice.offered_symbols():
        analyses_series = {}
        statuses = []
        timestamps = []
        for timeframe in provider.get_available_timeframes(symbol):
            result = load_market_data(
                provider,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                clock=clock,
                mode=Mode.RESEARCH,
            )
            statuses.append(result.report.status)
            if result.usable_series is not None:
                analyses_series[timeframe] = result.usable_series.closed_only()
                timestamps.append(result.report.checked_at)
        if not analyses_series:
            continue
        analyses = analyze_timeframes(analyses_series, selection)
        advice = advise_timeframe(analyses)
        risk_approved = False
        selected = (
            analyses.get(advice.recommended_timeframe) if advice.recommended_timeframe else None
        )
        if selected and selected.signal.entry is not None and selected.signal.stop is not None:
            try:
                calculate_ticket_sizing(
                    entry=selected.signal.entry,
                    stop=selected.signal.stop,
                    profile=settings.risk_profile(),
                )
                risk_approved = True
            except ValueError:
                pass
        data_status = max(statuses, key=lambda item: list(type(item)).index(item))
        opportunity = build_opportunity(
            symbol=symbol,
            advice=advice,
            analyses=analyses,
            data_status=data_status,
            risk_approved=risk_approved,
            timestamp=max(timestamps) if timestamps else datetime.now(UTC),
        )
        decisions.append(
            make_final_decision(
                opportunity,
                data_quality_approved=data_status is not DataStatus.BLOCKED,
                risk_approved=risk_approved,
                candles_closed=True,
                minimum_risk_reward=settings.risk_profile().min_risk_reward,
            )
        )
    st.session_state["final_decision_ranking"] = sorted(
        decisions, key=lambda item: (item.should_enter, item.confidence), reverse=True
    )

ranking = st.session_state.get("final_decision_ranking", [])
if ranking:
    rows = [
        {
            "Ativo": item.symbol,
            "Decisão": "ENTRADA" if item.should_enter else "NÃO ENTRAR",
            "Lado": ("COMPRA" if item.side == "BUY" else "VENDA" if item.side == "SELL" else "—"),
            "Timeframe": item.timeframe.value if item.timeframe else "—",
            "Confiança": item.confidence,
            "R:R": item.risk_reward,
        }
        for item in ranking
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    selected_symbol = st.selectbox("Abrir oportunidade", [item.symbol for item in ranking])
    selected = next(item for item in ranking if item.symbol == selected_symbol)
    st.markdown(f"### {selected.symbol} · {selected.state}")
    st.write(selected.primary_reason)
    with st.expander("Por que essa decisão?"):
        for reason in selected.reasons:
            st.write(f"• {reason}")
else:
    st.info("Atualize o ranking para avaliar os ativos disponíveis no provider.")
