"""Gestão determinística de posições abertas, separada da decisão de entrada.

O módulo não envia ordens e não altera persistência diretamente. Ele decide
HOLD/EXIT usando apenas candles fechados; a execução continua sob autoridade do
``PaperBroker``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from cashinho.domain.market import Candle, CandleSeries
from cashinho.pipeline.entry_signal import EntrySignal
from cashinho.pipeline.multi_timeframe import TimeframeAdvice
from cashinho.pipeline.paper_broker import PaperBroker, PaperOrder, PaperOrderStatus


class PositionAction(StrEnum):
    HOLD = "HOLD"
    EXIT = "EXIT"


class PositionExitReason(StrEnum):
    STOP = "STOP"
    TARGET = "TARGET"
    RISK_EXIT = "RISK_EXIT"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    OPPOSITE_SIGNAL = "OPPOSITE_SIGNAL"
    CONTEXT_REVERSAL = "CONTEXT_REVERSAL"


@dataclass(frozen=True, slots=True)
class PositionRiskState:
    """Conclusão já calculada pelo Risk Manager para a posição atual."""

    exit_required: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PositionDecision:
    action: PositionAction
    symbol: str
    side: str
    confidence: int
    current_price: Decimal | None
    stop: Decimal
    target: Decimal
    exit_price: Decimal | None
    primary_reason: str
    reasons: tuple[str, ...]
    timestamp: datetime
    exit_reason: PositionExitReason | None = None

    @property
    def can_execute(self) -> bool:
        """Saída dinâmica só é executável quando existe preço de book válido."""

        return self.action is PositionAction.EXIT and self.exit_price is not None


@dataclass(frozen=True, slots=True)
class _PositionSnapshot:
    symbol: str
    side: str
    current_price: Decimal | None
    stop: Decimal
    target: Decimal
    timestamp: datetime


def _stop_and_target(position: PaperOrder, candle: Candle) -> tuple[bool, bool]:
    ticket = position.ticket
    if ticket.side == "BUY":
        return candle.low <= ticket.stop, candle.high >= ticket.target
    return candle.high >= ticket.stop, candle.low <= ticket.target


def _relevant_context_reversal(
    side: str,
    advice: TimeframeAdvice | None,
    *,
    minimum_score: int,
) -> bool:
    opposite = "SELL" if side == "BUY" else "BUY"
    return bool(
        advice is not None
        and advice.side == opposite
        and advice.score >= minimum_score
        and advice.recommended_timeframe is not None
        and advice.rejection_reason is None
    )


def _thesis_invalidated(
    side: str,
    candles: tuple[Candle, ...],
    *,
    entry: Decimal,
) -> tuple[bool, str | None]:
    """Exige dois candles adversos; uma única oscilação nunca invalida a tese."""

    if len(candles) < 3:
        return False, None
    older, previous, last = candles[-3:]
    if side == "BUY":
        structure_lost = (
            previous.high < older.high
            and previous.low < older.low
            and last.high < previous.high
            and last.low < previous.low
        )
        important_region_lost = previous.close < entry and last.close < entry
        if structure_lost and important_region_lost:
            return True, "Estrutura de alta perdida e dois fechamentos confirmaram abaixo da entrada."
    else:
        structure_lost = (
            previous.high > older.high
            and previous.low > older.low
            and last.high > previous.high
            and last.low > previous.low
        )
        important_region_lost = previous.close > entry and last.close > entry
        if structure_lost and important_region_lost:
            return True, "Estrutura de baixa perdida e dois fechamentos confirmaram acima da entrada."
    return False, None


class PositionManager:
    """Decide se uma posição PAPER deve ser mantida ou encerrada."""

    def __init__(
        self,
        *,
        minimum_opposite_score: int = 75,
        minimum_context_reversal_score: int = 70,
    ) -> None:
        if not 0 <= minimum_opposite_score <= 100:
            raise ValueError("Score mínimo do sinal contrário deve estar entre 0 e 100.")
        if not 0 <= minimum_context_reversal_score <= 100:
            raise ValueError("Score mínimo da reversão deve estar entre 0 e 100.")
        self._minimum_opposite_score = minimum_opposite_score
        self._minimum_context_reversal_score = minimum_context_reversal_score

    def evaluate(
        self,
        position: PaperOrder,
        *,
        recent_candles: CandleSeries,
        technical_signal: EntrySignal | None,
        timeframe_advice: TimeframeAdvice | None,
        risk: PositionRiskState | None = None,
        current_price: Decimal | None = None,
        market_exit_price: Decimal | None = None,
    ) -> PositionDecision:
        if position.status is not PaperOrderStatus.OPEN:
            raise ValueError("Position Manager exige uma posição PAPER OPEN.")
        if position.ticket.side not in {"BUY", "SELL"}:
            raise ValueError("Lado da posição deve ser BUY ou SELL.")
        if market_exit_price is not None and market_exit_price <= 0:
            raise ValueError("Preço de saída de mercado deve ser maior que zero.")

        closed = recent_candles.closed_only()
        eligible = tuple(
            candle
            for candle in closed.candles
            if position.filled_at is None or candle.close_time > position.filled_at
        )
        last = eligible[-1] if eligible else None
        timestamp = (
            last.close_time
            if last is not None
            else position.filled_at or position.created_at
        )
        mark = current_price or (last.close if last is not None else position.fill_price)
        snapshot = _PositionSnapshot(
            symbol=position.ticket.symbol,
            side=position.ticket.side,
            current_price=mark,
            stop=position.ticket.stop,
            target=position.ticket.target,
            timestamp=timestamp,
        )

        if last is not None:
            stop_hit, target_hit = _stop_and_target(position, last)
            # Sem sequência intrabar, STOP é sempre o cenário conservador.
            if stop_hit:
                return self._decision(
                    snapshot,
                    PositionAction.EXIT,
                    confidence=100,
                    exit_price=position.ticket.stop,
                    primary_reason="Stop da posição foi atingido.",
                    reasons=("STOP tem prioridade sobre qualquer saída dinâmica.",),
                    exit_reason=PositionExitReason.STOP,
                )
            if target_hit:
                return self._decision(
                    snapshot,
                    PositionAction.EXIT,
                    confidence=100,
                    exit_price=position.ticket.target,
                    primary_reason="Alvo da posição foi atingido.",
                    reasons=("TARGET fixo foi confirmado por candle fechado.",),
                    exit_reason=PositionExitReason.TARGET,
                )

        risk_state = risk or PositionRiskState()
        if risk_state.exit_required:
            return self._dynamic_exit(
                snapshot,
                market_exit_price,
                PositionExitReason.RISK_EXIT,
                risk_state.reason or "Risk Manager exigiu o encerramento da posição.",
                confidence=100,
            )

        invalidated, invalidation_reason = _thesis_invalidated(
            position.ticket.side,
            eligible,
            entry=position.fill_price or position.ticket.entry,
        )
        if invalidated:
            return self._dynamic_exit(
                snapshot,
                market_exit_price,
                PositionExitReason.THESIS_INVALIDATED,
                invalidation_reason or "A tese original foi invalidada.",
                confidence=90,
            )

        context_reversed = _relevant_context_reversal(
            position.ticket.side,
            timeframe_advice,
            minimum_score=self._minimum_context_reversal_score,
        )
        opposite = "SELL" if position.ticket.side == "BUY" else "BUY"
        strong_opposite = bool(
            technical_signal is not None
            and technical_signal.side == opposite
            and technical_signal.status == "ENTRADA LIBERADA"
            and technical_signal.trigger_confirmed
            and technical_signal.score >= self._minimum_opposite_score
            and context_reversed
        )
        if strong_opposite:
            assert technical_signal is not None
            return self._dynamic_exit(
                snapshot,
                market_exit_price,
                PositionExitReason.OPPOSITE_SIGNAL,
                "Sinal contrário forte, com gatilho e contexto de reversão confirmados.",
                confidence=min(100, technical_signal.score),
            )
        if context_reversed:
            assert timeframe_advice is not None
            return self._dynamic_exit(
                snapshot,
                market_exit_price,
                PositionExitReason.CONTEXT_REVERSAL,
                "Contexto multi-timeframe virou de forma relevante contra a posição.",
                confidence=timeframe_advice.score,
            )

        reasons = ["Stop e alvo permanecem intactos."]
        if technical_signal is not None and technical_signal.side == opposite:
            reasons.append("Sinal contrário ainda não tem força e confirmação suficientes.")
        if timeframe_advice is not None and timeframe_advice.side == opposite:
            reasons.append("Conflito multi-timeframe ainda não caracteriza reversão relevante.")
        return self._decision(
            snapshot,
            PositionAction.HOLD,
            confidence=max(0, 100 - (timeframe_advice.score if timeframe_advice else 0) // 4),
            exit_price=None,
            primary_reason="A tese da posição continua válida.",
            reasons=tuple(reasons),
            exit_reason=None,
        )

    @staticmethod
    def _decision(
        snapshot: _PositionSnapshot,
        action: PositionAction,
        *,
        confidence: int,
        exit_price: Decimal | None,
        primary_reason: str,
        reasons: tuple[str, ...],
        exit_reason: PositionExitReason | None,
    ) -> PositionDecision:
        return PositionDecision(
            action=action,
            symbol=snapshot.symbol,
            side=snapshot.side,
            confidence=confidence,
            current_price=snapshot.current_price,
            stop=snapshot.stop,
            target=snapshot.target,
            exit_price=exit_price,
            primary_reason=primary_reason,
            reasons=reasons,
            timestamp=snapshot.timestamp,
            exit_reason=exit_reason,
        )

    @staticmethod
    def _dynamic_exit(
        snapshot: _PositionSnapshot,
        market_exit_price: Decimal | None,
        reason: PositionExitReason,
        primary_reason: str,
        *,
        confidence: int,
    ) -> PositionDecision:
        reasons = [primary_reason]
        if market_exit_price is None:
            reasons.append("Saída recomendada; execução aguarda bid/ask ativo e válido.")
        return PositionManager._decision(
            snapshot,
            PositionAction.EXIT,
            confidence=confidence,
            exit_price=market_exit_price,
            primary_reason=primary_reason,
            reasons=tuple(reasons),
            exit_reason=reason,
        )


def apply_position_decision(
    broker: PaperBroker,
    position: PaperOrder,
    decision: PositionDecision,
) -> PaperOrder | None:
    """Entrega uma saída dinâmica executável ao PaperBroker; nunca reverte posição."""

    if decision.action is PositionAction.HOLD or not decision.can_execute:
        return None
    if decision.exit_reason in {PositionExitReason.STOP, PositionExitReason.TARGET}:
        # Estes estados pertencem a process_candle(), que conserva STOPPED/TARGETED.
        return None
    assert decision.exit_price is not None
    assert decision.exit_reason is not None
    return broker.close_position(
        position.id,
        price=decision.exit_price,
        closed_at=decision.timestamp,
        reason=decision.exit_reason.value,
    )
