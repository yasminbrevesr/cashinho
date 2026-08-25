"""Backtest cronológico da FinalDecision de produção."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import streamlit as st

from app.components.backtest_results import render_backtest_result
from app.components.chrome import page_header, sidebar
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.domain.enums import Mode
from cashinho.domain.errors import CashinhoError
from cashinho.pipeline.backtest import (
    ExecutionCostModel,
    PipelineDecisionEvaluator,
    run_backtest,
    temporal_split,
)
from cashinho.pipeline.indicators import IndicatorSelection
from cashinho.pipeline.market_data import load_market_data

settings = get_settings()
clock = SystemClock()
sidebar(settings)
page_header("Backtest", "Validação histórica candle a candle da FinalDecision")

st.warning(
    "Resultados históricos não garantem resultados futuros. O backtest é somente analítico e "
    "não envia ordens.",
    icon="⚠️",
)

choice = build_market_data_provider(
    settings, clock, fixtures_root=settings.data_dir / "fixtures"
)
symbols = choice.offered_symbols()
if not symbols:
    st.error("Nenhum ativo histórico está disponível para backtest.")
    st.stop()

input_row = st.columns(3)
symbol = input_row[0].selectbox("Ativo", symbols)
today = clock.now().date()
start_date = input_row[1].date_input(
    "Início", value=today - timedelta(days=90), format="DD/MM/YYYY"
)
end_date = input_row[2].date_input("Fim", value=today, format="DD/MM/YYYY")
if start_date > end_date:
    st.error("A data inicial não pode ser posterior à final.")
    st.stop()

capital_row = st.columns(4)
capital = Decimal(
    str(
        capital_row[0].number_input(
            "Capital inicial (R$)", min_value=1.0, value=float(settings.capital), step=100.0
        )
    )
)
spread = Decimal(
    str(capital_row[1].number_input("Spread por unidade", min_value=0.0, value=0.0, step=0.01))
)
slippage = Decimal(
    str(
        capital_row[2].number_input(
            "Slippage por unidade", min_value=0.0, value=0.0, step=0.01
        )
    )
)
fixed_fee = Decimal(
    str(capital_row[3].number_input("Taxa fixa por ordem", min_value=0.0, value=0.0, step=0.01))
)

split_row = st.columns(3)
train_pct = int(split_row[0].number_input("TRAIN (%)", 10, 80, 60, 5))
validation_pct = int(split_row[1].number_input("VALIDATION (%)", 10, 40, 20, 5))
test_pct = 100 - train_pct - validation_pct
split_row[2].metric("TEST (%)", test_pct)
if test_pct <= 0:
    st.error("TRAIN + VALIDATION deve deixar uma amostra TEST positiva.")
    st.stop()

st.caption(
    "A divisão é temporal e contígua. TEST serve apenas para avaliação; não há otimização "
    "de parâmetros nesta versão."
)

if st.button("EXECUTAR BACKTEST", type="primary", use_container_width=True):
    start = datetime.combine(start_date, time.min, tzinfo=UTC)
    end = datetime.combine(end_date, time.min, tzinfo=UTC) + timedelta(days=1)
    series_by_timeframe = {}
    blocked: list[str] = []
    with st.spinner("Processando candles fechados cronologicamente..."):
        try:
            available = choice.provider.get_available_timeframes(symbol)
            for timeframe in available:
                loaded = load_market_data(
                    choice.provider,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                    clock=clock,
                    mode=Mode.BACKTEST,
                )
                if loaded.usable_series is None:
                    blocked.append(f"{timeframe.value}: {loaded.rejection_reason or 'Data Quality'}")
                else:
                    series_by_timeframe[timeframe] = loaded.usable_series
        except CashinhoError as exc:
            st.error(f"Falha ao carregar histórico: {exc}")
            st.stop()

        if len(series_by_timeframe) < 2:
            st.error(
                "O backtest da FinalDecision exige ao menos dois timeframes aprovados pelo "
                "Data Quality."
            )
            if blocked:
                st.caption(" · ".join(blocked))
            st.stop()

        profile = settings.risk_profile().model_copy(update={"capital": capital})
        selection = IndicatorSelection(
            ema_periods=(9, 21),
            vwap=True,
            rsi_period=14,
            macd=True,
            atr_period=14,
        )
        evaluator = PipelineDecisionEvaluator(
            selection,
            profile,
            data_quality_approved=not blocked,
        )
        cost_model = ExecutionCostModel(
            spread=spread,
            slippage=slippage,
            fixed_fee_per_order=fixed_fee,
        )
        overall = run_backtest(
            series_by_timeframe,
            evaluator,
            risk_profile=profile,
            costs=cost_model,
        )
        samples = temporal_split(
            series_by_timeframe,
            train_pct=train_pct,
            validation_pct=validation_pct,
        )
        segmented = {
            label: run_backtest(sample, evaluator, risk_profile=profile, costs=cost_model)
            for label, sample in samples.items()
            if any(len(series) for series in sample.values())
        }
    st.session_state["backtest_results"] = {
        "capital": capital,
        "overall": overall,
        "segments": segmented,
    }

saved = st.session_state.get("backtest_results")
if saved:
    tabs = st.tabs(["GERAL", "TRAIN", "VALIDATION", "TEST"])
    with tabs[0]:
        render_backtest_result(saved["overall"], initial_capital=saved["capital"])
    for tab, label in zip(tabs[1:], ("TRAIN", "VALIDATION", "TEST"), strict=True):
        with tab:
            result = saved["segments"].get(label)
            if result is None:
                st.info("Amostra sem candles suficientes.")
            else:
                render_backtest_result(result, initial_capital=saved["capital"])
