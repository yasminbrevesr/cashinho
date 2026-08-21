"""Semantica dos enums centrais."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.domain.enums import DataStatus, Mode, OpportunityState, Timeframe


def test_modo_padrao_e_paper_no_settings_default() -> None:
    from cashinho.config.settings import Settings

    assert Settings(_env_file=None).mode is Mode.PAPER


@pytest.mark.parametrize("mode", [Mode.ASSISTED, Mode.LIVE])
def test_modos_que_tocam_dinheiro_real(mode: Mode) -> None:
    assert mode.touches_real_money


@pytest.mark.parametrize("mode", [Mode.RESEARCH, Mode.BACKTEST, Mode.REPLAY, Mode.PAPER])
def test_modos_que_nao_tocam_dinheiro_real(mode: Mode) -> None:
    assert not mode.touches_real_money


def test_backtest_e_replay_nao_exigem_tempo_real() -> None:
    assert not Mode.BACKTEST.requires_realtime_data
    assert not Mode.REPLAY.requires_realtime_data
    assert Mode.PAPER.requires_realtime_data


def test_duracao_dos_timeframes() -> None:
    assert Timeframe.M1.duration == timedelta(minutes=1)
    assert Timeframe.H1.duration == timedelta(hours=1)
    assert Timeframe.D1.duration == timedelta(days=1)


def test_apenas_diario_nao_e_intradiario() -> None:
    intraday = [tf for tf in Timeframe if tf.is_intraday]
    assert Timeframe.D1 not in intraday
    assert len(intraday) == len(Timeframe) - 1


def test_estados_terminais() -> None:
    assert OpportunityState.NAO_OPERAR.is_terminal
    assert OpportunityState.REJEITADO.is_terminal
    assert OpportunityState.EXPIRADO.is_terminal
    assert not OpportunityState.AGUARDANDO_GATILHO.is_terminal
    assert not OpportunityState.APROVADO.is_terminal


def test_somente_setup_aprovado_permite_execucao() -> None:
    permitidos = [s for s in OpportunityState if s.allows_execution]
    assert permitidos == [OpportunityState.APROVADO]


def test_status_bloqueado_impede_analise() -> None:
    assert not DataStatus.BLOCKED.allows_analysis
    assert DataStatus.OK.allows_analysis
    assert DataStatus.DEGRADED.allows_analysis
