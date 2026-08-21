"""Capacidade do provedor limitando o modo de operacao (decisao D9).

Um provedor com cotacao atrasada nao pode habilitar decisao intradiaria ao
vivo. O bloqueio e estrutural, nao depende de disciplina do operador.
"""

from __future__ import annotations

import pytest

from cashinho.domain.enums import Mode, Timeframe
from cashinho.ports.market_data import ProviderCapabilities

ATRASADO = ProviderCapabilities(
    name="atrasado",
    supports_realtime=False,
    typical_delay_seconds=900,
    min_timeframe=Timeframe.M15,
    intraday_history_days=30,
)

TEMPO_REAL = ProviderCapabilities(
    name="tempo_real",
    supports_realtime=True,
    typical_delay_seconds=1,
    min_timeframe=Timeframe.M1,
    supports_quotes=True,
)


@pytest.mark.parametrize("mode", [Mode.PAPER, Mode.ASSISTED, Mode.LIVE])
def test_provedor_atrasado_nao_habilita_modos_ao_vivo(mode: Mode) -> None:
    assert not ATRASADO.allows_mode(mode)
    assert ATRASADO.rejection_reason(mode, Timeframe.M15) is not None


@pytest.mark.parametrize("mode", [Mode.RESEARCH, Mode.BACKTEST, Mode.REPLAY])
def test_provedor_atrasado_serve_para_pesquisa_e_historico(mode: Mode) -> None:
    assert ATRASADO.allows_mode(mode)
    assert ATRASADO.rejection_reason(mode, Timeframe.M15) is None


def test_provedor_em_tempo_real_habilita_paper() -> None:
    assert TEMPO_REAL.allows_mode(Mode.PAPER)
    assert TEMPO_REAL.rejection_reason(Mode.PAPER, Timeframe.M1) is None


def test_timeframe_abaixo_do_minimo_e_recusado() -> None:
    assert not ATRASADO.supports(Timeframe.M1)
    assert not ATRASADO.supports(Timeframe.M5)
    motivo = ATRASADO.rejection_reason(Mode.RESEARCH, Timeframe.M1)
    assert motivo is not None
    assert "1m" in motivo


def test_timeframe_igual_ou_maior_que_o_minimo_e_aceito() -> None:
    assert ATRASADO.supports(Timeframe.M15)
    assert ATRASADO.supports(Timeframe.H1)
    assert ATRASADO.supports(Timeframe.D1)


def test_motivo_de_modo_tem_prioridade_sobre_timeframe() -> None:
    motivo = ATRASADO.rejection_reason(Mode.PAPER, Timeframe.M1)
    assert motivo is not None
    assert "tempo real" in motivo


def test_padroes_sao_conservadores() -> None:
    """Provedor que nao declara capacidade nao habilita nada ao vivo."""
    minimo = ProviderCapabilities(name="desconhecido")
    assert not minimo.supports_realtime
    assert not minimo.supports_quotes
    assert minimo.min_timeframe is Timeframe.D1
    assert not minimo.allows_mode(Mode.PAPER)
