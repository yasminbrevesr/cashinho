"""Os estados que cada camada pode assumir.

Vocabulario fechado: uma camada nao devolve texto livre, devolve um destes
valores. E' o que permite escrever regras verificaveis - e testa-las.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from ...models import Direction


class Vies(str, Enum):
    """Para que lado a camada aponta."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

    @property
    def direcao(self) -> Optional[Direction]:
        if self is Vies.BULLISH:
            return Direction.LONG
        if self is Vies.BEARISH:
            return Direction.SHORT
        return None

    @property
    def oposto(self) -> "Vies":
        if self is Vies.BULLISH:
            return Vies.BEARISH
        if self is Vies.BEARISH:
            return Vies.BULLISH
        return Vies.NEUTRAL

    @classmethod
    def de_direcao(cls, direcao: Optional[Direction]) -> "Vies":
        if direcao is Direction.LONG:
            return cls.BULLISH
        if direcao is Direction.SHORT:
            return cls.BEARISH
        return cls.NEUTRAL


class ContextState(str, Enum):
    """Timeframe maior: o pano de fundo do dia."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

    @property
    def vies(self) -> Vies:
        return {
            ContextState.BULLISH: Vies.BULLISH,
            ContextState.BEARISH: Vies.BEARISH,
            ContextState.NEUTRAL: Vies.NEUTRAL,
        }[self]


class TrendState(str, Enum):
    """Timeframe intermediario: a direcao dominante agora."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"

    @property
    def vies(self) -> Vies:
        return {
            TrendState.BULLISH: Vies.BULLISH,
            TrendState.BEARISH: Vies.BEARISH,
            TrendState.SIDEWAYS: Vies.NEUTRAL,
        }[self]


class SetupState(str, Enum):
    """Timeframe de operacao: que formacao esta no grafico."""

    PULLBACK = "pullback"
    BREAKOUT = "breakout"
    FAILED_BREAKOUT = "failed_breakout"
    RANGE_EDGE = "range_edge"
    NONE = "none"

    @property
    def existe(self) -> bool:
        return self is not SetupState.NONE


class TriggerState(str, Enum):
    """Timeframe de gatilho: o que aconteceu no ultimo candle fechado."""

    BREAKOUT_WITH_VOLUME = "breakout_with_volume"
    MA_RECLAIM = "ma_reclaim"
    REJECTION_WICK = "rejection_wick"
    NONE = "none"

    @property
    def existe(self) -> bool:
        return self is not TriggerState.NONE


PAPEIS_PADRAO = ("context", "trend", "setup", "trigger")
"""Os quatro papeis na ordem do maior para o menor timeframe."""

ESTADOS_POR_PAPEL = {
    "context": ContextState,
    "trend": TrendState,
    "setup": SetupState,
    "trigger": TriggerState,
}
