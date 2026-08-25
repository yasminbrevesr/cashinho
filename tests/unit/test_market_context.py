from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cashinho.domain.enums import DataStatus, Timeframe
from cashinho.domain.market import Candle, CandleSeries
from cashinho.pipeline.entry_signal import EntrySignal
from cashinho.pipeline.market_regime import MarketRegime, RegimeAnalysis, analyze_market_regime
from cashinho.pipeline.multi_timeframe import TimeframeAdvice, TimeframeAnalysis, advise_timeframe
from cashinho.pipeline.opportunities import Opportunity, build_opportunity, rank_opportunities


def series(kind: str, *, open_tail: bool = False) -> CandleSeries:
    start = datetime(2026, 8, 20, 10, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(30):
        if kind == "up":
            price = Decimal("10") + Decimal(index) / Decimal("10")
            width = Decimal("0.10")
        elif kind == "down":
            price = Decimal("13") - Decimal(index) / Decimal("10")
            width = Decimal("0.10")
        elif kind == "volatile":
            price = Decimal("10")
            width = Decimal("2") if index >= 25 else Decimal("0.10")
        else:
            price = Decimal("10") + (Decimal("0.02") if index % 2 else Decimal("0"))
            width = Decimal("0.10")
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=5 * index),
                close_time=start + timedelta(minutes=5 * (index + 1)),
                open=price,
                high=price + width,
                low=price - width,
                close=price,
                volume=1000,
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


def test_regimes_deterministicos() -> None:
    assert analyze_market_regime(series("up")).regime is MarketRegime.TREND_UP
    assert analyze_market_regime(series("down")).regime is MarketRegime.TREND_DOWN
    assert analyze_market_regime(series("range")).regime is MarketRegime.RANGE
    assert analyze_market_regime(series("volatile")).regime is MarketRegime.HIGH_VOLATILITY


def test_regime_indeterminado_e_sem_lookahead() -> None:
    short = series("up").model_copy(update={"candles": series("up").candles[:10]})
    assert analyze_market_regime(short).regime is MarketRegime.INDETERMINATE
    assert analyze_market_regime(series("up", open_tail=True)) == analyze_market_regime(
        series("up")
    )


def analysis(timeframe: Timeframe, direction: str, score: int = 80) -> TimeframeAnalysis:
    regime = MarketRegime.TREND_UP if direction == "BUY" else MarketRegime.TREND_DOWN
    return TimeframeAnalysis(
        timeframe,
        RegimeAnalysis(regime, 80, direction, 80, "TREND", "NORMAL", (), {}),
        EntrySignal(
            direction,
            "ENTRADA LIBERADA",
            score,
            Decimal("10"),
            Decimal("9"),
            Decimal("12"),
            2.0,
            (),
            True,
        ),
    )


def test_alinhamento_e_selecao_de_timeframe() -> None:
    analyses = {
        Timeframe.D1: analysis(Timeframe.D1, "BUY"),
        Timeframe.H1: analysis(Timeframe.H1, "BUY"),
        Timeframe.M15: analysis(Timeframe.M15, "BUY", 70),
        Timeframe.M5: analysis(Timeframe.M5, "BUY", 90),
        Timeframe.M1: analysis(Timeframe.M1, "BUY", 60),
    }
    advice = advise_timeframe(analyses)
    assert advice.recommended_timeframe is Timeframe.M5
    assert advice.trigger_timeframe is Timeframe.M1
    assert advice.side == "BUY"


def test_conflito_multi_timeframe_bloqueia() -> None:
    analyses = {
        Timeframe.H1: analysis(Timeframe.H1, "BUY"),
        Timeframe.M15: analysis(Timeframe.M15, "BUY"),
        Timeframe.M5: analysis(Timeframe.M5, "SELL"),
    }
    advice = advise_timeframe(analyses)
    assert advice.recommended_timeframe is None
    assert advice.rejection_reason is not None


def opportunity(symbol: str, score: int, rejected: bool = False) -> Opportunity:
    return Opportunity(
        symbol,
        "BUY",
        MarketRegime.TREND_UP,
        Timeframe.M5,
        (Timeframe.H1,),
        Timeframe.M1,
        score,
        Decimal("10"),
        Decimal("9"),
        Decimal("12"),
        2.0,
        True,
        (),
        ("blocked",) if rejected else (),
        datetime(2026, 8, 20, tzinfo=UTC),
    )


def test_ranking_prioriza_score_e_nunca_aprova_bloqueada() -> None:
    ranked = rank_opportunities([opportunity("B", 90, True), opportunity("A", 70)])
    assert ranked[0].symbol == "A"
    assert ranked[1].score == 0
    assert not ranked[1].trigger_confirmed


def test_data_quality_e_risk_manager_bloqueiam_oportunidade() -> None:
    analyses = {Timeframe.M5: analysis(Timeframe.M5, "BUY")}
    advice = TimeframeAdvice(Timeframe.M5, (Timeframe.H1,), Timeframe.M1, 80, "BUY", ())
    result = build_opportunity(
        symbol="PETR4",
        advice=advice,
        analyses=analyses,
        data_status=DataStatus.BLOCKED,
        risk_approved=False,
        timestamp=datetime(2026, 8, 20, tzinfo=UTC),
    )
    assert result.state == "NÃO OPERAR"
    assert len(result.rejection_reasons) == 2
