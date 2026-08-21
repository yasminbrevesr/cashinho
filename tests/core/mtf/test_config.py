"""A combinacao de timeframes e' configuracao, nao codigo."""

from __future__ import annotations

import pytest

from cashinho.core.mtf import CAMADAS_PADRAO, ConfiguracaoInvalidaError, MTFConfig, SESSAO_B3


def test_padrao_usa_60_15_5_1():
    c = MTFConfig.padrao()
    assert c.camadas == {"contexto": "60m", "tendencia": "15m", "setup": "5m", "gatilho": "1m"}
    assert CAMADAS_PADRAO["contexto"] == "60m"


def test_papeis_vao_do_maior_para_o_menor_timeframe():
    c = MTFConfig.padrao()
    assert c.papeis() == ["contexto", "tendencia", "setup", "gatilho"]
    assert c.contexto == "contexto"
    assert c.gatilho == "gatilho"


def test_camadas_podem_ser_trocadas_por_completo():
    c = MTFConfig(
        base="1m",
        camadas={"macro": "1d", "diretor": "30m", "entrada": "3m"},
    )
    assert c.papeis() == ["macro", "diretor", "entrada"]
    assert c.gatilho == "entrada"
    assert c.timeframes() == ["1d", "30m", "3m", "1m"]  # a base entra na lista


def test_numero_de_camadas_e_livre():
    duas = MTFConfig(base="5m", camadas={"tendencia": "30m", "gatilho": "5m"})
    assert duas.papeis() == ["tendencia", "gatilho"]

    cinco = MTFConfig(
        base="1m",
        camadas={"a": "1d", "b": "60m", "c": "15m", "d": "5m", "e": "1m"},
    )
    assert len(cinco.papeis()) == 5


def test_1h_e_60m_sao_o_mesmo_timeframe():
    c = MTFConfig(base="1m", camadas={"contexto": "1h", "gatilho": "1m"})
    assert c.camadas["contexto"] == "60m"
    assert c.papel_de("60m") == "contexto"
    assert c.papel_de("1h") == "contexto"


def test_camada_que_nao_e_multiplo_da_base_e_recusada():
    with pytest.raises(ConfiguracaoInvalidaError) as exc:
        MTFConfig(base="5m", camadas={"setup": "7m", "gatilho": "5m"})
    assert "multiplo" in str(exc.value)


def test_timeframe_invalido_e_recusado():
    with pytest.raises(ConfiguracaoInvalidaError):
        MTFConfig(base="1m", camadas={"gatilho": "5 minutos"})


def test_sem_camadas_e_recusado():
    with pytest.raises(ConfiguracaoInvalidaError):
        MTFConfig(base="1m", camadas={})


def test_rotulagem_invalida_e_recusada():
    with pytest.raises(ConfiguracaoInvalidaError):
        MTFConfig(rotulagem="meio-do-candle")


def test_camada_inexistente_da_erro_com_dica():
    c = MTFConfig.padrao()
    with pytest.raises(ConfiguracaoInvalidaError) as exc:
        c.timeframe("swing")
    assert "contexto" in str(exc.value)


def test_ida_e_volta_por_dicionario():
    original = MTFConfig(
        base="1m",
        camadas={"contexto": "30m", "gatilho": "1m"},
        rotulagem="fechamento",
    )
    copia = MTFConfig.de_dict(original.para_dict())

    assert copia.camadas == original.camadas
    assert copia.rotulagem == "fechamento"
    assert copia.sessao.abertura == SESSAO_B3.abertura
    assert copia.sessao.fechamento == SESSAO_B3.fechamento


def test_sessao_vem_do_dicionario():
    c = MTFConfig.de_dict(
        {"base": "1m", "camadas": {"gatilho": "1m"}, "sessao": {"abertura": "09:00", "fechamento": "18:25"}}
    )
    assert c.sessao.abertura.hour == 9
    assert c.sessao.fechamento.hour == 18
    assert c.sessao.duracao_minutos() == 565
