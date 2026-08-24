"""Estado do dado e capacidades declaradas."""

from __future__ import annotations

import pytest

from cashinho.data.status import (
    Capacidades,
    CapacidadeAusenteError,
    StatusDados,
    exigir,
    pior_status,
)


def test_os_cinco_estados_pedidos():
    assert [e.value for e in StatusDados] == [
        "ONLINE", "DELAYED", "STALE", "DEGRADED", "OFFLINE"]


def test_so_online_serve_para_tempo_real():
    """DELAYED nao serve por definicao: a propria fonte declara o atraso."""
    assert StatusDados.ONLINE.serve_para_tempo_real is True
    for outro in (StatusDados.DELAYED, StatusDados.STALE,
                  StatusDados.DEGRADED, StatusDados.OFFLINE):
        assert outro.serve_para_tempo_real is False


def test_delayed_e_stale_tem_dado_offline_nao():
    assert StatusDados.DELAYED.tem_dado is True
    assert StatusDados.STALE.tem_dado is True
    assert StatusDados.OFFLINE.tem_dado is False


def test_o_aviso_proibe_uso_em_tempo_real():
    assert "NAO UTILIZAR PARA ENTRADA EM TEMPO REAL" in StatusDados.DELAYED.aviso
    assert "NAO UTILIZAR PARA ENTRADA EM TEMPO REAL" in StatusDados.STALE.aviso
    assert StatusDados.ONLINE.aviso == ""


def test_o_pior_estado_vence():
    assert pior_status(StatusDados.ONLINE, StatusDados.STALE) is StatusDados.STALE
    assert pior_status() is StatusDados.OFFLINE


# --- capacidades ---------------------------------------------------------


def test_capacidade_nao_declarada_nao_existe():
    """O padrao e' 'nao sei fazer nada'."""
    c = Capacidades()

    assert c.candles_historicos is False
    assert c.serve_para_day_trade is False


def test_day_trade_exige_tempo_real_1m_e_atraso_pequeno():
    completo = Capacidades(cotacao_em_tempo_real=True, intradiario_1m=True,
                           atraso_tipico_s=0.5)

    assert completo.serve_para_day_trade is True


def test_atraso_desconhecido_nao_serve_para_day_trade():
    """Nao saber o atraso e' motivo para nao usar."""
    c = Capacidades(cotacao_em_tempo_real=True, intradiario_1m=True,
                    atraso_tipico_s=None)

    assert c.serve_para_day_trade is False


def test_atraso_grande_nao_serve_para_day_trade():
    c = Capacidades(cotacao_em_tempo_real=True, intradiario_1m=True,
                    atraso_tipico_s=900)

    assert c.serve_para_day_trade is False


def test_timeframe_nao_declarado_e_desconhecido_e_nao_falso():
    """'Nao declarou' e 'nao suporta' sao coisas diferentes."""
    assert Capacidades().suporta("1m") is None
    assert Capacidades(timeframes=("1d",)).suporta("1m") is False
    assert Capacidades(timeframes=("1d",)).suporta("1d") is True


def test_a_barreira_recusa_capacidade_ausente():
    with pytest.raises(CapacidadeAusenteError, match="nao declara"):
        exigir(Capacidades(), "teste", livro_de_ofertas=True)


def test_a_barreira_deixa_passar_o_que_foi_declarado():
    exigir(Capacidades(candles_historicos=True), "teste", candles_historicos=True)


def test_a_mensagem_diz_o_que_falta():
    with pytest.raises(CapacidadeAusenteError) as e:
        exigir(Capacidades(), "brapi", intradiario_1m=True, livro_de_ofertas=True)

    assert "intradiario_1m" in str(e.value) and "livro_de_ofertas" in str(e.value)
