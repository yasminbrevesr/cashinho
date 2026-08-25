from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from cashinho.core.indicators import IndicatorResult
from cashinho.domain.enums import Timeframe
from cashinho.domain.market import Candle, CandleSeries
from cashinho.pipeline.entry_signal import evaluate_entry_signal
from cashinho.pipeline.indicators import IndicatorPanel, IndicatorSelection, compute_panel


def _series(*, trigger: bool, open_tail: bool = False) -> CandleSeries:
    start = datetime(2026, 8, 20, 10, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(30):
        base = Decimal("10") + Decimal(index) / Decimal("10")
        close = base + (Decimal("0.20") if trigger and index == 29 else Decimal("0.05"))
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=5 * index),
                close_time=start + timedelta(minutes=5 * (index + 1)),
                open=base,
                high=close,
                low=base - Decimal("0.05"),
                close=close,
                volume=5000 if trigger and index == 29 else 1000,
            )
        )
    if open_tail:
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=150),
                close_time=start + timedelta(minutes=155),
                open=Decimal("1"),
                high=Decimal("100"),
                low=Decimal("1"),
                close=Decimal("100"),
                volume=999999,
                is_closed=False,
            )
        )
    return CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=tuple(candles),
        source="test",
        fetched_at=start + timedelta(minutes=151),
    )


def _result(name: str, value: float) -> IndicatorResult:
    return IndicatorResult(
        name=name,
        symbol="PETR4",
        timeframe=Timeframe.M5,
        values=pd.DataFrame({name: [value]}),
        warmup=0,
    )


def _panel() -> IndicatorPanel:
    return IndicatorPanel(
        overlays={
            "EMA(9)": _result("ema9", 12),
            "EMA(21)": _result("ema21", 11),
            "VWAP": _result("vwap", 11),
        },
        oscillators={"RSI(14)": _result("rsi", 60)},
    )


def test_contexto_sem_gatilho_aguarda() -> None:
    signal = evaluate_entry_signal(_series(trigger=False), _panel())
    assert signal.status == "AGUARDANDO GATILHO"
    assert signal.entry is None


def test_contexto_e_gatilho_liberam_buy_com_geometria_valida() -> None:
    signal = evaluate_entry_signal(_series(trigger=True), _panel())
    assert signal.status == "ENTRADA LIBERADA"
    assert signal.trigger_confirmed
    assert signal.stop is not None and signal.entry is not None and signal.target is not None
    assert signal.stop < signal.entry < signal.target


def test_candle_em_formacao_nao_altera_sinal() -> None:
    closed = evaluate_entry_signal(_series(trigger=True), _panel())
    with_open = evaluate_entry_signal(_series(trigger=True, open_tail=True), _panel())
    assert with_open == closed


def test_indicadores_descartam_candle_em_formacao() -> None:
    panel = compute_panel(
        _series(trigger=True, open_tail=True), IndicatorSelection(ema_periods=(9,))
    )
    assert len(panel.overlays["EMA(9)"].values) == 30
