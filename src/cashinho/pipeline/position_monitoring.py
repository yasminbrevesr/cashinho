"""Orquestra análise técnica existente para uma posição PAPER aberta."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cashinho.domain.enums import Timeframe
from cashinho.domain.market import CandleSeries
from cashinho.pipeline.indicators import IndicatorSelection
from cashinho.pipeline.multi_timeframe import (
    TimeframeAdvice,
    advise_timeframe,
    analyze_timeframes,
)
from cashinho.pipeline.paper_broker import PaperOrder
from cashinho.pipeline.position_manager import (
    PositionDecision,
    PositionManager,
    PositionRiskState,
)


@dataclass(frozen=True, slots=True)
class PositionMonitoringResult:
    decision: PositionDecision
    advice: TimeframeAdvice
    operational_timeframe: Timeframe


def evaluate_open_position(
    position: PaperOrder,
    *,
    series_by_timeframe: dict[Timeframe, CandleSeries],
    selection: IndicatorSelection,
    manager: PositionManager | None = None,
    risk: PositionRiskState | None = None,
    current_price: Decimal | None = None,
    market_exit_price: Decimal | None = None,
) -> PositionMonitoringResult:
    """Converte séries fechadas em HOLD/EXIT sem duplicar regras na UI."""

    if not series_by_timeframe:
        raise ValueError("Monitoramento de posição exige ao menos uma série.")
    if any(series.symbol != position.ticket.symbol for series in series_by_timeframe.values()):
        raise ValueError("Todas as séries devem pertencer ao ativo da posição.")
    closed = {timeframe: series.closed_only() for timeframe, series in series_by_timeframe.items()}
    analyses = analyze_timeframes(closed, selection)
    advice = advise_timeframe(analyses)

    ticket_timeframe: Timeframe | None = None
    if position.ticket.timeframe is not None:
        try:
            ticket_timeframe = Timeframe(position.ticket.timeframe)
        except ValueError:
            ticket_timeframe = None
    operational = (
        ticket_timeframe
        if ticket_timeframe in analyses
        else advice.recommended_timeframe
        if advice.recommended_timeframe in analyses
        else min(analyses, key=lambda timeframe: timeframe.duration)
    )
    technical_signal = analyses[operational].signal
    decision = (manager or PositionManager()).evaluate(
        position,
        recent_candles=closed[operational],
        technical_signal=technical_signal,
        timeframe_advice=advice,
        risk=risk,
        current_price=current_price,
        market_exit_price=market_exit_price,
    )
    return PositionMonitoringResult(decision, advice, operational)
