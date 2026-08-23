"""Os estados e o caderno de anotacoes."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.saude import EstadoDeSaude, Modo, Telemetria, pior_de

from .factories import AGORA


# --- estados -------------------------------------------------------------


def test_os_tres_estados_pedidos_existem():
    assert {e.value for e in EstadoDeSaude} == {"ONLINE", "DEGRADED", "OFFLINE"}


def test_so_online_e_saudavel():
    assert EstadoDeSaude.ONLINE.saudavel is True
    assert EstadoDeSaude.DEGRADED.saudavel is False
    assert EstadoDeSaude.OFFLINE.saudavel is False


def test_o_conjunto_vale_pelo_pior_componente():
    """Um painel que mostra verde porque a media deu bom nao serve para nada."""
    assert pior_de([EstadoDeSaude.ONLINE, EstadoDeSaude.DEGRADED]) is EstadoDeSaude.DEGRADED
    assert pior_de([EstadoDeSaude.ONLINE, EstadoDeSaude.OFFLINE]) is EstadoDeSaude.OFFLINE
    assert pior_de([EstadoDeSaude.ONLINE]) is EstadoDeSaude.ONLINE


def test_conjunto_vazio_nao_e_saudavel():
    assert pior_de([]) is EstadoDeSaude.OFFLINE


def test_o_modo_real_e_o_unico_que_envia_ordem_de_verdade():
    assert Modo.REAL.envia_ordem_de_verdade is True
    for modo in (Modo.ANALISE, Modo.PAPER, Modo.REPLAY, Modo.BACKTEST):
        assert modo.envia_ordem_de_verdade is False


# --- telemetria ------------------------------------------------------------


def test_registra_sucesso_com_latencia_e_timestamp():
    t = Telemetria(relogio=lambda: AGORA)
    t.sucesso("market_data", latencia_ms=250, dado_em=AGORA - timedelta(minutes=1))

    assert t.latencia_ms("market_data") == 250
    assert t.ultimo_dado("market_data") == AGORA - timedelta(minutes=1)
    assert t.ultimo_ok("market_data") == AGORA


def test_a_latencia_e_a_mediana_para_uma_medicao_ruim_nao_virar_alarme():
    t = Telemetria(relogio=lambda: AGORA)
    for ms in (100, 120, 110, 9000):
        t.sucesso("market_data", latencia_ms=ms)

    assert t.latencia_ms("market_data") == 115


def test_componente_sem_anotacao_nao_tem_latencia():
    assert Telemetria().latencia_ms("scanner") is None


def test_registra_erro_com_hora_e_origem():
    t = Telemetria(relogio=lambda: AGORA)
    e = t.erro("news", "timeout")

    assert e.componente == "news"
    assert e.quando == AGORA
    assert t.erros("news") == [e]


def test_os_erros_saem_do_mais_recente_para_o_mais_antigo():
    momento = AGORA
    t = Telemetria(relogio=lambda: momento)
    t.erro("news", "primeiro")
    momento = AGORA + timedelta(minutes=5)
    t.erro("news", "segundo")

    assert [e.mensagem for e in t.erros("news")] == ["segundo", "primeiro"]


def test_erros_recentes_respeitam_a_janela():
    momento = AGORA - timedelta(hours=2)
    t = Telemetria(relogio=lambda: momento)
    t.erro("news", "antigo")
    momento = AGORA
    t.erro("news", "novo")

    recentes = t.erros_recentes("news", minutos=30, agora=AGORA)
    assert [e.mensagem for e in recentes] == ["novo"]


def test_erros_sem_componente_juntam_todos():
    t = Telemetria(relogio=lambda: AGORA)
    t.erro("news", "a")
    t.erro("scanner", "b")

    assert len(t.erros()) == 2


def test_o_caderno_de_erros_nao_cresce_para_sempre():
    t = Telemetria(relogio=lambda: AGORA)
    for i in range(100):
        t.erro("market_data", f"erro {i}")

    assert len(t.erros("market_data")) <= 20


def test_marco_guarda_o_horario_da_ultima_analise():
    t = Telemetria(relogio=lambda: AGORA)
    t.marco("analise")

    assert t.ultimo_marco("analise") == AGORA
    assert t.ultimo_marco("nunca") is None
