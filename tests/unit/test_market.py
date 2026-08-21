"""Candle e CandleSeries: coerencia OHLC, ordenacao e candle fechado."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from cashinho.core.time.clocks import FrozenClock
from cashinho.domain.enums import Timeframe
from cashinho.domain.errors import LookaheadError, UnclosedCandleError
from cashinho.domain.market import Candle, CandleSeries, Quote
from tests.conftest import REFERENCE_INSTANT, make_candle, make_series


def test_candle_valido() -> None:
    candle = make_candle(REFERENCE_INSTANT)
    assert candle.is_closed
    assert candle.range == Decimal("0.20")


def test_high_menor_que_close_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="high"):
        Candle(
            open_time=REFERENCE_INSTANT,
            close_time=REFERENCE_INSTANT + timedelta(minutes=5),
            open=Decimal("10.00"),
            high=Decimal("9.50"),
            low=Decimal("9.00"),
            close=Decimal("10.00"),
            volume=100,
        )


def test_low_maior_que_open_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="low"):
        Candle(
            open_time=REFERENCE_INSTANT,
            close_time=REFERENCE_INSTANT + timedelta(minutes=5),
            open=Decimal("10.00"),
            high=Decimal("11.00"),
            low=Decimal("10.50"),
            close=Decimal("10.80"),
            volume=100,
        )


def test_close_time_anterior_a_open_time_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="close_time"):
        Candle(
            open_time=REFERENCE_INSTANT,
            close_time=REFERENCE_INSTANT - timedelta(minutes=5),
            open=Decimal("10.00"),
            high=Decimal("10.00"),
            low=Decimal("10.00"),
            close=Decimal("10.00"),
            volume=100,
        )


def test_volume_negativo_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Candle(
            open_time=REFERENCE_INSTANT,
            close_time=REFERENCE_INSTANT + timedelta(minutes=5),
            open=Decimal("10.00"),
            high=Decimal("10.00"),
            low=Decimal("10.00"),
            close=Decimal("10.00"),
            volume=-1,
        )


def test_serie_rejeita_candle_duplicado() -> None:
    candle = make_candle(REFERENCE_INSTANT)
    with pytest.raises(ValidationError, match="duplicado"):
        CandleSeries(
            symbol="PETR4",
            timeframe=Timeframe.M5,
            candles=(candle, candle),
            source="fixture",
            fetched_at=REFERENCE_INSTANT,
        )


def test_serie_rejeita_ordem_invertida() -> None:
    primeiro = make_candle(REFERENCE_INSTANT)
    anterior = make_candle(REFERENCE_INSTANT - timedelta(minutes=5))
    with pytest.raises(ValidationError, match="fora de ordem"):
        CandleSeries(
            symbol="PETR4",
            timeframe=Timeframe.M5,
            candles=(primeiro, anterior),
            source="fixture",
            fetched_at=REFERENCE_INSTANT,
        )


def test_apenas_o_ultimo_candle_pode_estar_aberto() -> None:
    aberto = make_candle(REFERENCE_INSTANT - timedelta(minutes=10), is_closed=False)
    fechado = make_candle(REFERENCE_INSTANT - timedelta(minutes=5))
    with pytest.raises(ValidationError, match="aberto"):
        CandleSeries(
            symbol="PETR4",
            timeframe=Timeframe.M5,
            candles=(aberto, fechado),
            source="fixture",
            fetched_at=REFERENCE_INSTANT,
        )


def test_closed_only_descarta_candle_em_formacao() -> None:
    serie = make_series(count=5, last_open=True)
    assert serie.has_open_candle
    fechada = serie.closed_only()
    assert len(fechada) == 4
    assert not fechada.has_open_candle


def test_closed_only_e_idempotente_em_serie_fechada() -> None:
    serie = make_series(count=5)
    assert serie.closed_only() == serie


def test_require_closed_falha_com_candle_aberto() -> None:
    serie = make_series(count=3, last_open=True)
    with pytest.raises(UnclosedCandleError, match="candle fechado"):
        serie.require_closed()


def test_require_closed_passa_com_serie_fechada() -> None:
    serie = make_series(count=3)
    assert serie.require_closed() is serie


def test_lookahead_e_detectado() -> None:
    """Candle fechado no futuro do relogio logico e informacao indisponivel."""
    serie = make_series(count=3, end=REFERENCE_INSTANT + timedelta(hours=2))
    clock = FrozenClock(REFERENCE_INSTANT)
    with pytest.raises(LookaheadError, match="posterior ao instante logico"):
        serie.assert_no_lookahead(clock)


def test_serie_passada_nao_dispara_lookahead() -> None:
    serie = make_series(count=3, end=REFERENCE_INSTANT)
    clock = FrozenClock(REFERENCE_INSTANT + timedelta(hours=1))
    assert serie.assert_no_lookahead(clock) is serie


def test_to_frame_indexado_em_utc() -> None:
    frame = make_series(count=4).to_frame()
    assert len(frame) == 4
    assert str(frame.index.tz) == "UTC"
    assert list(frame.columns) == ["open", "high", "low", "close", "volume", "is_closed"]
    assert frame["close"].dtype.kind == "f"


def test_to_frame_de_serie_vazia() -> None:
    serie = CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=(),
        source="fixture",
        fetched_at=REFERENCE_INSTANT,
    )
    frame = serie.to_frame()
    assert frame.empty
    assert serie.is_empty
    assert serie.last is None


def test_quote_calcula_idade() -> None:
    quote = Quote(
        symbol="PETR4",
        price=Decimal("10.00"),
        timestamp=REFERENCE_INSTANT,
        source="fixture",
        latency_ms=120,
    )
    clock = FrozenClock(REFERENCE_INSTANT + timedelta(seconds=30))
    assert quote.age_seconds(clock) == 30.0


def test_datetime_naive_em_candle_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="naive"):
        Candle(
            open_time=datetime(2026, 8, 20, 14, 0),
            close_time=datetime(2026, 8, 20, 14, 5, tzinfo=UTC),
            open=Decimal("10.00"),
            high=Decimal("10.00"),
            low=Decimal("10.00"),
            close=Decimal("10.00"),
            volume=1,
        )


def test_to_records_expoe_os_nove_campos() -> None:
    """Forma plana: symbol, timestamp, OHLC, volume, timeframe, source."""
    registros = make_series(count=3).to_records()
    assert len(registros) == 3
    assert set(registros[0]) == {
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "timeframe",
        "source",
    }
    assert registros[0]["symbol"] == "PETR4"
    assert registros[0]["timeframe"] == "5m"
    assert registros[0]["source"] == "fixture"


def test_timestamp_e_a_abertura_do_candle() -> None:
    candle = make_candle(REFERENCE_INSTANT)
    assert candle.timestamp == candle.open_time
    assert candle.timestamp != candle.close_time
