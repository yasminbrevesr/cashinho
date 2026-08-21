"""Montagem do painel de indicadores.

Fica no pipeline, e nao na tela: decidir quais indicadores calcular, com
que parametros e o que fazer quando faltam dados e regra de aplicacao.
A tela apenas escolhe as opcoes e desenha o resultado.

Consequencia pratica: esta logica e testavel sem subir o Streamlit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from cashinho.core.indicators import (
    IndicatorNotApplicableError,
    IndicatorResult,
    InsufficientDataError,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    sma,
    vwap,
)
from cashinho.domain.market import CandleSeries
from cashinho.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IndicatorSelection:
    """Quais indicadores calcular e com que parametros."""

    sma_periods: tuple[int, ...] = ()
    ema_periods: tuple[int, ...] = ()
    vwap: bool = False
    bollinger_period: int | None = None
    bollinger_deviations: float = 2.0
    rsi_period: int | None = None
    macd: bool = False
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int | None = None

    @property
    def any_selected(self) -> bool:
        return bool(
            self.sma_periods
            or self.ema_periods
            or self.vwap
            or self.bollinger_period
            or self.rsi_period
            or self.macd
            or self.atr_period
        )


@dataclass(frozen=True, slots=True)
class IndicatorPanel:
    """Indicadores calculados e os que nao puderam ser calculados.

    As falhas voltam junto, com o motivo. Omiti-las faria um indicador
    ausente por falta de dados parecer identico a um indicador que o
    usuario nao pediu — e as duas situacoes exigem reacoes diferentes.
    """

    overlays: dict[str, IndicatorResult] = field(default_factory=dict)
    oscillators: dict[str, IndicatorResult] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def has_content(self) -> bool:
        return bool(self.overlays or self.oscillators)


def compute_panel(series: CandleSeries, selection: IndicatorSelection) -> IndicatorPanel:
    """Calcula os indicadores selecionados.

    Falha de um indicador nao derruba os demais: se a serie tem 30
    candles, a EMA(9) e valida mesmo que o MACD(12,26,9) nao seja.
    """
    overlays: dict[str, IndicatorResult] = {}
    oscillators: dict[str, IndicatorResult] = {}
    failures: dict[str, str] = {}

    def run(
        label: str,
        target: dict[str, IndicatorResult],
        func: Callable[[], IndicatorResult],
    ) -> None:
        try:
            target[label] = func()
        except (InsufficientDataError, IndicatorNotApplicableError) as exc:
            failures[label] = str(exc)
            logger.info(
                "indicador nao calculado",
                extra={"symbol": series.symbol, "indicator": label, "reason": str(exc)},
            )

    for period in selection.sma_periods:
        run(f"SMA({period})", overlays, partial(sma, series, period))

    for period in selection.ema_periods:
        run(f"EMA({period})", overlays, partial(ema, series, period))

    if selection.vwap:
        run("VWAP", overlays, lambda: vwap(series))

    if selection.bollinger_period:
        run(
            f"BB({selection.bollinger_period})",
            overlays,
            lambda: bollinger(
                series,
                selection.bollinger_period or 20,
                deviations=selection.bollinger_deviations,
            ),
        )

    if selection.rsi_period:
        run(
            f"RSI({selection.rsi_period})",
            oscillators,
            lambda: rsi(series, selection.rsi_period or 14),
        )

    if selection.macd:
        run(
            "MACD",
            oscillators,
            lambda: macd(
                series,
                fast=selection.macd_fast,
                slow=selection.macd_slow,
                signal=selection.macd_signal,
            ),
        )

    if selection.atr_period:
        run(
            f"ATR({selection.atr_period})",
            oscillators,
            lambda: atr(series, selection.atr_period or 14),
        )

    return IndicatorPanel(overlays=overlays, oscillators=oscillators, failures=failures)
