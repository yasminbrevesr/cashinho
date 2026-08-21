"""Implementacoes da porta Clock.

Tres implementacoes cobrem os seis modos:

- `SystemClock`  — RESEARCH, PAPER, ASSISTED (tempo real)
- `FrozenClock`  — testes deterministicos
- `ReplayClock`  — REPLAY e BACKTEST (tempo logico controlado)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cashinho.domain.types import ensure_utc


class SystemClock:
    """Relogio do sistema operacional, em UTC."""

    kind = "SystemClock"

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Relogio parado em um instante fixo.

    Usado em testes: qualquer comportamento dependente de tempo passa a
    ser deterministico e reproduzivel.
    """

    kind = "FrozenClock"

    def __init__(self, instant: datetime) -> None:
        self._instant = ensure_utc(instant)

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        """Reposiciona o relogio."""
        self._instant = ensure_utc(instant)


class ReplayClock:
    """Relogio de tempo logico, avancado explicitamente.

    Durante a reproducao de um pregao historico, o algoritmo so pode
    conhecer o que existia neste instante. O avanco e responsabilidade do
    motor de replay, nunca da estrategia.
    """

    kind = "ReplayClock"

    def __init__(self, start: datetime) -> None:
        self._start = ensure_utc(start)
        self._instant = self._start

    def now(self) -> datetime:
        return self._instant

    @property
    def start(self) -> datetime:
        return self._start

    def advance(self, delta: timedelta) -> datetime:
        """Avanca o tempo logico. Retrocesso e erro."""
        if delta < timedelta(0):
            raise ValueError("ReplayClock nao retrocede: delta deve ser positivo")
        self._instant = self._instant + delta
        return self._instant

    def advance_to(self, instant: datetime) -> datetime:
        """Salta para um instante especifico, que nao pode ser anterior."""
        target = ensure_utc(instant)
        if target < self._instant:
            raise ValueError(
                f"ReplayClock nao retrocede: alvo {target.isoformat()} e anterior "
                f"ao instante atual {self._instant.isoformat()}"
            )
        self._instant = target
        return self._instant
