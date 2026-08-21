"""Relogios: determinismo e proibicao de retrocesso."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cashinho.core.time.clocks import FrozenClock, ReplayClock, SystemClock
from cashinho.ports.clock import Clock

REF = datetime(2026, 8, 20, 17, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "clock", [SystemClock(), FrozenClock(REF), ReplayClock(REF)]
)
def test_implementacoes_satisfazem_a_porta(clock: Clock) -> None:
    assert isinstance(clock, Clock)
    assert clock.now().tzinfo is not None


def test_system_clock_retorna_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_frozen_clock_nao_avanca_sozinho() -> None:
    clock = FrozenClock(REF)
    assert clock.now() == clock.now() == REF


def test_frozen_clock_normaliza_fuso() -> None:
    from datetime import timezone

    clock = FrozenClock(datetime(2026, 8, 20, 14, 30, tzinfo=timezone(timedelta(hours=-3))))
    assert clock.now() == REF


def test_replay_clock_avanca() -> None:
    clock = ReplayClock(REF)
    assert clock.advance(timedelta(minutes=5)) == REF + timedelta(minutes=5)
    assert clock.now() == REF + timedelta(minutes=5)


def test_replay_clock_nao_retrocede_por_delta() -> None:
    clock = ReplayClock(REF)
    with pytest.raises(ValueError, match="nao retrocede"):
        clock.advance(timedelta(minutes=-1))


def test_replay_clock_nao_retrocede_por_alvo() -> None:
    clock = ReplayClock(REF)
    clock.advance(timedelta(minutes=10))
    with pytest.raises(ValueError, match="nao retrocede"):
        clock.advance_to(REF)


def test_replay_clock_preserva_o_inicio() -> None:
    clock = ReplayClock(REF)
    clock.advance(timedelta(hours=2))
    assert clock.start == REF
