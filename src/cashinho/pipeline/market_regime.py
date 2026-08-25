"""Classificacao deterministica e explicavel do contexto de mercado."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cashinho.domain.market import CandleSeries


class MarketRegime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    EXPANSION = "EXPANSION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class RegimeAnalysis:
    regime: MarketRegime
    confidence: int
    direction: str
    strength: int
    structure: str
    volatility: str
    reasons: tuple[str, ...]
    metrics: dict[str, float]


def analyze_market_regime(series: CandleSeries) -> RegimeAnalysis:
    candles = series.closed_only().candles
    if len(candles) < 20:
        return RegimeAnalysis(
            MarketRegime.INDETERMINATE,
            0,
            "NONE",
            0,
            "INDETERMINATE",
            "UNKNOWN",
            ("Menos de 20 candles fechados.",),
            {"candles": float(len(candles))},
        )

    recent = candles[-20:]
    closes = [float(c.close) for c in recent]
    ranges = [float(c.high - c.low) for c in recent]
    volumes = [float(c.volume) for c in recent]
    fast = sum(closes[-5:]) / 5
    slow = sum(closes) / 20
    average_range = sum(ranges[:-5]) / 15
    recent_range = sum(ranges[-5:]) / 5
    range_ratio = recent_range / average_range if average_range else 0.0
    average_volume = sum(volumes[:-5]) / 15
    volume_ratio = (sum(volumes[-5:]) / 5) / average_volume if average_volume else 0.0
    price_distance = abs(closes[-1] - slow) / slow if slow else 0.0

    higher = sum(
        current.high > previous.high and current.low > previous.low
        for previous, current in zip(recent[-7:-1], recent[-6:], strict=True)
    )
    lower = sum(
        current.high < previous.high and current.low < previous.low
        for previous, current in zip(recent[-7:-1], recent[-6:], strict=True)
    )
    reasons: list[str] = []
    regime = MarketRegime.RANGE
    direction = "NONE"
    confidence = 55
    structure = "LATERAL"

    if range_ratio >= 2.0:
        regime = MarketRegime.HIGH_VOLATILITY
        confidence = min(100, int(55 + (range_ratio - 2) * 20))
        reasons.append("Amplitude recente muito acima da média.")
    elif range_ratio >= 1.35 and volume_ratio >= 1.2:
        regime = MarketRegime.EXPANSION
        confidence = min(100, int(55 + range_ratio * 15))
        reasons.append("Expansão de amplitude confirmada por volume.")
    elif higher >= 4 and fast > slow and closes[-1] > slow:
        regime, direction, structure = MarketRegime.TREND_UP, "BUY", "ASCENDENTE"
        confidence = min(100, 55 + higher * 7)
        reasons.extend(("Máximas e mínimas ascendentes.", "Média curta acima da média longa."))
    elif lower >= 4 and fast < slow and closes[-1] < slow:
        regime, direction, structure = MarketRegime.TREND_DOWN, "SELL", "DESCENDENTE"
        confidence = min(100, 55 + lower * 7)
        reasons.extend(("Máximas e mínimas descendentes.", "Média curta abaixo da média longa."))
    else:
        reasons.append("Estrutura sem predominância direcional suficiente.")

    volatility = "HIGH" if range_ratio >= 1.7 else "LOW" if range_ratio <= 0.7 else "NORMAL"
    metrics = {
        "fast_average": fast,
        "slow_average": slow,
        "range_ratio": range_ratio,
        "volume_ratio": volume_ratio,
        "price_distance": price_distance,
        "higher_structure_count": float(higher),
        "lower_structure_count": float(lower),
    }
    return RegimeAnalysis(
        regime,
        confidence,
        direction,
        confidence,
        structure,
        volatility,
        tuple(reasons),
        metrics,
    )
