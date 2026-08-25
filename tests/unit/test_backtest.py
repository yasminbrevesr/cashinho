from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cashinho.domain.enums import Timeframe
from cashinho.domain.errors import LookaheadError
from cashinho.domain.market import Candle, CandleSeries
from cashinho.domain.risk import RiskProfile
from cashinho.pipeline.backtest import (
    BacktestTrade,
    ExecutionCostModel,
    PipelineDecisionEvaluator,
    calculate_metrics,
    run_backtest,
    temporal_split,
)
from cashinho.pipeline.final_decision import FinalDecision
from cashinho.pipeline.indicators import IndicatorSelection
from tests.conftest import REFERENCE_INSTANT, make_series

START = datetime(2026, 8, 20, 10, tzinfo=UTC)


def market_candle(index: int, *, low: str, high: str, closed: bool = True) -> Candle:
    opened = START + timedelta(minutes=5 * index)
    midpoint = (Decimal(low) + Decimal(high)) / Decimal("2")
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=5),
        open=midpoint,
        high=Decimal(high),
        low=Decimal(low),
        close=midpoint,
        volume=100,
        is_closed=closed,
    )


def series(*candles: Candle) -> CandleSeries:
    return CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=candles,
        source="test",
        fetched_at=START + timedelta(days=1),
    )


class FirstDecision:
    def __init__(self, side: str = "BUY") -> None:
        self.side = side
        self.calls = 0
        self.seen_close_times: list[datetime] = []

    def evaluate(
        self,
        series_by_timeframe: dict[Timeframe, CandleSeries],
        *,
        as_of: datetime,
    ) -> FinalDecision:
        self.calls += 1
        current = series_by_timeframe[Timeframe.M5]
        self.seen_close_times.extend(c.close_time for c in current.candles)
        enter = self.calls == 1
        stop, target = (("9", "12") if self.side == "BUY" else ("11", "8"))
        return FinalDecision(
            should_enter=enter,
            side=self.side if enter else "NONE",
            symbol="PETR4",
            timeframe=Timeframe.M5,
            confidence=80,
            entry=Decimal("10") if enter else None,
            stop=Decimal(stop) if enter else None,
            target=Decimal(target) if enter else None,
            risk_reward=2.0 if enter else None,
            primary_reason="teste",
            reasons=("teste",),
            timestamp=as_of,
        )


PROFILE = RiskProfile(
    capital=Decimal("1000"),
    risk_per_trade_pct=Decimal("1"),
    max_exposure_per_symbol_pct=Decimal("100"),
)


@pytest.mark.parametrize(
    ("side", "low", "high", "reason", "expected"),
    [
        ("BUY", "9.5", "12.5", "TARGET", Decimal("20.00")),
        ("BUY", "8.5", "10.5", "STOP", Decimal("-10.00")),
        ("SELL", "7.5", "10.5", "TARGET", Decimal("20.00")),
        ("SELL", "9.5", "11.5", "STOP", Decimal("-10.00")),
    ],
)
def test_backtest_buy_sell_stop_target(
    side: str, low: str, high: str, reason: str, expected: Decimal
) -> None:
    data = series(
        market_candle(0, low="9.8", high="10.2"),
        market_candle(1, low=low, high=high),
    )
    result = run_backtest({Timeframe.M5: data}, FirstDecision(side), risk_profile=PROFILE)
    assert len(result.trades) == 1
    assert result.trades[0].close_reason == reason
    assert result.trades[0].net_pnl == expected
    assert result.trades[0].result_in_r == (Decimal("2.00") if expected > 0 else Decimal("-1.00"))


def test_stop_e_alvo_no_mesmo_candle_prioriza_stop() -> None:
    data = series(
        market_candle(0, low="9.8", high="10.2"),
        market_candle(1, low="8", high="13"),
    )
    trade = run_backtest({Timeframe.M5: data}, FirstDecision(), risk_profile=PROFILE).trades[0]
    assert trade.close_reason == "STOP"


def test_entrada_nao_tocada_nao_cria_trade() -> None:
    data = series(
        market_candle(0, low="9.8", high="10.2"),
        market_candle(1, low="10.5", high="11.5"),
    )
    result = run_backtest({Timeframe.M5: data}, FirstDecision(), risk_profile=PROFILE)
    assert result.trades == ()
    assert result.unfilled_signals == 1


def test_sem_lookahead_e_candle_aberto_ignorado() -> None:
    evaluator = FirstDecision()
    evaluator.calls = 1  # nunca libera entrada; avalia todos os prefixes
    data = series(
        market_candle(0, low="9.8", high="10.2"),
        market_candle(1, low="9.8", high="10.2"),
        market_candle(2, low="9.8", high="10.2", closed=False),
    )
    run_backtest({Timeframe.M5: data}, evaluator, risk_profile=PROFILE)
    assert evaluator.seen_close_times
    assert max(evaluator.seen_close_times) <= data.candles[1].close_time


def test_avaliador_da_final_decision_rejeita_serie_futura() -> None:
    evaluator = PipelineDecisionEvaluator(IndicatorSelection(), PROFILE)
    data = {
        Timeframe.H1: make_series(35, timeframe=Timeframe.H1),
        Timeframe.M5: make_series(35, timeframe=Timeframe.M5),
    }
    with pytest.raises(LookaheadError):
        evaluator.evaluate(data, as_of=REFERENCE_INSTANT - timedelta(hours=2))


def test_avaliador_historico_retorna_a_final_decision_de_producao() -> None:
    evaluator = PipelineDecisionEvaluator(IndicatorSelection(), PROFILE)
    data = {
        Timeframe.H1: make_series(35, timeframe=Timeframe.H1),
        Timeframe.M5: make_series(35, timeframe=Timeframe.M5),
    }
    decision = evaluator.evaluate(data, as_of=REFERENCE_INSTANT)
    assert isinstance(decision, FinalDecision)
    assert decision.timestamp <= REFERENCE_INSTANT


def trade(net: str, result_r: str, index: int) -> BacktestTrade:
    value = Decimal(net)
    return BacktestTrade(
        symbol="PETR4",
        side="BUY",
        timeframe=Timeframe.M5,
        signal_at=START,
        entered_at=START + timedelta(minutes=index * 10),
        exited_at=START + timedelta(minutes=index * 10 + 5),
        planned_entry=Decimal("10"),
        stop=Decimal("9"),
        target=Decimal("12"),
        entry_price=Decimal("10"),
        exit_price=Decimal("10") + value,
        quantity=1,
        close_reason="TARGET" if value > 0 else "STOP",
        gross_pnl=value,
        costs=Decimal("0"),
        net_pnl=value,
        pnl_pct=value * Decimal("10"),
        result_in_r=Decimal(result_r),
        duration=timedelta(minutes=5),
    )


def test_metricas_profit_factor_expectancy_e_drawdown() -> None:
    metrics, _, _ = calculate_metrics(
        [trade("20", "2", 0), trade("-10", "-1", 1), trade("-10", "-1", 2)],
        initial_capital=Decimal("100"),
    )
    assert metrics.profit_factor == Decimal("1.00")
    assert metrics.expectancy == Decimal("0.00")
    assert metrics.max_drawdown == Decimal("20.00")
    assert metrics.total_r == Decimal("0.00")


def test_modelo_de_custos_reduz_resultado() -> None:
    data = series(
        market_candle(0, low="9.8", high="10.2"),
        market_candle(1, low="9.5", high="12.5"),
    )
    result = run_backtest(
        {Timeframe.M5: data},
        FirstDecision(),
        risk_profile=PROFILE,
        costs=ExecutionCostModel(spread=Decimal("0.10"), slippage=Decimal("0.05")),
    )
    assert result.trades[0].net_pnl < result.trades[0].gross_pnl


def test_split_temporal_60_20_20() -> None:
    candles = tuple(market_candle(i, low="9.8", high="10.2") for i in range(10))
    split = temporal_split({Timeframe.M5: series(*candles)})
    assert [len(split[label][Timeframe.M5]) for label in ("TRAIN", "VALIDATION", "TEST")] == [
        6,
        2,
        2,
    ]
    assert split["TRAIN"][Timeframe.M5].last.close_time < split["VALIDATION"][Timeframe.M5].candles[0].close_time  # type: ignore[union-attr]
