"""Fixtures compartilhadas.

Toda dependencia de tempo nos testes passa por `FrozenClock`: nenhum teste
do Cashinho pode depender do relogio do sistema, sob pena de falhar de
forma intermitente e mascarar regressoes de look-ahead.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from cashinho.adapters.persistence.session import build_session_factory, init_db
from cashinho.core.time.clocks import FrozenClock
from cashinho.domain.enums import Timeframe
from cashinho.domain.market import Candle, CandleSeries

REFERENCE_INSTANT = datetime(2026, 8, 20, 17, 30, tzinfo=UTC)
"""20/08/2026, 14:30 em Sao Paulo — pregao aberto."""


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(REFERENCE_INSTANT)


def make_candle(
    open_time: datetime,
    *,
    timeframe: Timeframe = Timeframe.M5,
    close: str = "10.00",
    volume: int = 1000,
    is_closed: bool = True,
) -> Candle:
    """Constroi um candle coerente a partir de um preco de fechamento."""
    price = Decimal(close)
    return Candle(
        open_time=open_time,
        close_time=open_time + timeframe.duration,
        open=price,
        high=price + Decimal("0.10"),
        low=price - Decimal("0.10"),
        close=price,
        volume=volume,
        is_closed=is_closed,
    )


def make_series(
    count: int = 5,
    *,
    timeframe: Timeframe = Timeframe.M5,
    end: datetime = REFERENCE_INSTANT,
    last_open: bool = False,
    symbol: str = "PETR4",
) -> CandleSeries:
    """Serie contigua terminando em `end`.

    Se `last_open` for True, o ultimo candle representa o periodo ainda em
    formacao — util para testar o invariante de candle fechado.
    """
    step = timeframe.duration
    first_open = end - step * count
    candles = [
        make_candle(
            first_open + step * i,
            timeframe=timeframe,
            close=f"{10 + i * 0.1:.2f}",
            is_closed=not (last_open and i == count - 1),
        )
        for i in range(count)
    ]
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        source="fixture",
        fetched_at=end,
    )


@pytest.fixture
def series() -> CandleSeries:
    return make_series()


@pytest.fixture
def series_with_open_candle() -> CandleSeries:
    return make_series(last_open=True)


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Banco em memoria, isolado por teste."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://", future=True)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    return build_session_factory(sqlite_engine)


@pytest.fixture
def future_instant() -> datetime:
    return REFERENCE_INSTANT + timedelta(hours=1)
