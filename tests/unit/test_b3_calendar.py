"""Sessao de negociacao da B3."""

from __future__ import annotations

from datetime import UTC, date, datetime

from cashinho.core.time.b3_calendar import B3Calendar

CAL = B3Calendar()


def _utc(y: int, m: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def test_conversao_para_horario_local() -> None:
    local = CAL.to_local(_utc(2026, 8, 20, 17, 30))
    assert (local.hour, local.minute) == (14, 30)


def test_pregao_aberto_no_meio_da_sessao() -> None:
    assert CAL.is_open(_utc(2026, 8, 20, 17, 30))


def test_pregao_fechado_antes_da_abertura() -> None:
    assert not CAL.is_open(_utc(2026, 8, 20, 12, 0))


def test_fechamento_e_exclusivo() -> None:
    """17:00 local ja e fora do pregao regular."""
    assert not CAL.is_open(_utc(2026, 8, 20, 20, 0))
    assert CAL.is_open(_utc(2026, 8, 20, 19, 59))


def test_fim_de_semana_nao_e_dia_de_pregao() -> None:
    assert not CAL.is_trading_day(date(2026, 8, 22))
    assert not CAL.is_trading_day(date(2026, 8, 23))
    assert CAL.is_trading_day(date(2026, 8, 20))


def test_feriado_injetado_e_respeitado() -> None:
    cal = B3Calendar(holidays=frozenset({date(2026, 9, 7)}))
    assert not cal.is_trading_day(date(2026, 9, 7))
    assert cal.holidays_loaded


def test_calendario_sem_feriados_declara_a_limitacao() -> None:
    assert not CAL.holidays_loaded


def test_limites_da_sessao_em_utc() -> None:
    bounds = CAL.session_bounds(date(2026, 8, 20))
    assert bounds is not None
    abertura, fechamento = bounds
    assert abertura == _utc(2026, 8, 20, 13, 0)
    assert fechamento == _utc(2026, 8, 20, 20, 0)


def test_sem_sessao_em_fim_de_semana() -> None:
    assert CAL.session_bounds(date(2026, 8, 22)) is None
