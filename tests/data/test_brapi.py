"""O provedor brapi - todo testado com resposta simulada, sem tocar na rede."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from cashinho.data.base import DataError
from cashinho.data.brapi import BrapiError, BrapiMarketDataProvider
from cashinho.data.status import StatusDados
from cashinho.models import BRT
from cashinho.settings import ConfigMarketData

from .factories import AGORA, abridor, config_brapi, resposta_brapi


def provider(corpo=None, registro=None, config=None, agora=AGORA, **campos):
    return BrapiMarketDataProvider(
        config or config_brapi(**campos),
        abrir=abridor(corpo if corpo is not None else resposta_brapi(), registro),
        relogio=lambda: agora,
    )


# --- requisicao ------------------------------------------------------------


def test_usa_a_url_base_e_o_endpoint_de_quote():
    registro = []
    provider(registro=registro).cotacao("PETR4")

    url, _ = registro[0]
    assert url.startswith("https://brapi.dev/api/quote/PETR4")


def test_manda_o_token_no_cabecalho_e_nunca_na_url():
    registro = []
    provider(registro=registro).cotacao("PETR4")

    url, cabecalhos = registro[0]
    assert cabecalhos["Authorization"] == "Bearer token-de-teste"
    assert "token-de-teste" not in url


def test_sem_token_nao_manda_cabecalho_de_autorizacao():
    registro = []
    provider(registro=registro, brapi_token="").cotacao("PETR4")

    assert "Authorization" not in registro[0][1]


def test_o_historico_manda_range_e_interval():
    registro = []
    provider(registro=registro).candles("PETR4", "1d", 30)

    url, _ = registro[0]
    assert "interval=1d" in url
    assert "range=" in url


# --- cotacao ---------------------------------------------------------------


def test_normaliza_a_cotacao():
    cot = provider().cotacao("PETR4")

    assert cot.symbol == "PETR4"
    assert cot.last == 38.42
    assert cot.previous_close == 37.8
    assert cot.source == "brapi"


def test_o_book_fica_none_porque_a_fonte_nao_entrega():
    """Campo que a fonte nao da nao e' inventado."""
    cot = provider().cotacao("PETR4")

    assert cot.bid is None and cot.ask is None
    assert cot.spread is None


def test_plano_com_atraso_declarado_sai_delayed():
    cot = provider().cotacao("PETR4")

    assert cot.status is StatusDados.DELAYED
    assert cot.serve_para_tempo_real is False
    assert "NAO UTILIZAR PARA ENTRADA EM TEMPO REAL" in cot.aviso


def test_a_idade_do_dado_e_calculada():
    cot = provider().cotacao("PETR4")

    assert cot.data_age == pytest.approx(900, abs=1)
    assert "15 min" in cot.idade_legivel


def test_dado_muito_alem_do_atraso_prometido_vira_stale():
    corpo = resposta_brapi(momento=AGORA - timedelta(hours=6))

    assert provider(corpo).cotacao("PETR4").status is StatusDados.STALE


# --- capacidades vem da configuracao ------------------------------------------


def test_sem_atraso_declarado_nao_serve_para_tempo_real():
    """O Cashinho nao chuta caracteristica de plano."""
    p = provider(brapi_atraso_s=None)

    assert p.capacidades.cotacao_em_tempo_real is False
    assert p.capacidades.serve_para_day_trade is False


def test_timeframes_vem_da_configuracao():
    p = provider(brapi_timeframes=("1d", "1wk"))

    assert p.capacidades.timeframes == ("1d", "1wk")
    assert p.capacidades.intradiario_1m is False


def test_1m_declarado_liga_a_capacidade_intradiaria():
    p = provider(brapi_timeframes=("1m", "1d"))

    assert p.capacidades.intradiario_1m is True


def test_timeframe_nao_declarado_e_recusado():
    with pytest.raises(BrapiError, match="nao esta em BRAPI_TIMEFRAMES"):
        provider().candles("PETR4", "5m", 10)


def test_sem_timeframe_declarado_o_provedor_recusa_em_vez_de_chutar():
    with pytest.raises(BrapiError, match="BRAPI_TIMEFRAMES"):
        provider(brapi_timeframes=()).candles("PETR4", "1d", 10)


# --- candles ------------------------------------------------------------------


def test_normaliza_os_candles():
    serie = provider().candles("PETR4", "1d", 10)

    assert len(serie) == 5
    assert serie.symbol == "PETR4" and serie.timeframe == "1d"
    assert all(c.ts.tzinfo is not None for c in serie.candles)


def test_os_candles_saem_em_ordem():
    ts = [c.ts for c in provider().candles("PETR4", "1d", 10).candles]

    assert ts == sorted(ts)


def test_linha_incoerente_e_descartada_sem_derrubar_a_serie():
    corpo = json.loads(resposta_brapi())
    corpo["results"][0]["historicalDataPrice"].append(
        {"date": int(AGORA.timestamp()), "open": 30, "high": 29, "low": 31,
         "close": 30, "volume": 1})   # maxima abaixo da minima
    serie = provider(json.dumps(corpo)).candles("PETR4", "1d", 10)

    assert len(serie) == 5


def test_historico_vazio_vira_erro():
    corpo = json.loads(resposta_brapi())
    corpo["results"][0]["historicalDataPrice"] = []

    with pytest.raises(BrapiError, match="historico vazio"):
        provider(json.dumps(corpo)).candles("PETR4", "1d", 10)


# --- campos ausentes: falha alta, nunca adivinhacao -------------------------------


def test_campo_obrigatorio_ausente_explica_o_que_fazer():
    corpo = json.loads(resposta_brapi())
    del corpo["results"][0]["historicalDataPrice"]

    with pytest.raises(BrapiError) as e:
        provider(json.dumps(corpo)).candles("PETR4", "1d", 10)

    assert "CAMPOS" in str(e.value)
    assert "adivinhacao" in str(e.value)


def test_apelido_alternativo_de_campo_funciona():
    """A documentacao nao pode ser aberta daqui: o parser aceita apelidos."""
    corpo = json.loads(resposta_brapi())
    dados = corpo["results"][0]
    dados["price"] = dados.pop("regularMarketPrice")

    assert provider(json.dumps(corpo)).cotacao("PETR4").last == 38.42


# --- erros de rede e protocolo ------------------------------------------------------


def test_resposta_sem_results_vira_erro():
    with pytest.raises(BrapiError, match="sem resultado"):
        provider(json.dumps({"results": []})).cotacao("PETR4")


def test_resposta_que_nao_e_json_vira_erro():
    with pytest.raises(BrapiError, match="nao e' JSON"):
        provider("<html>manutencao</html>").cotacao("PETR4")


def test_erro_de_credencial_diz_o_que_conferir():
    p = provider()
    erro = p._erro_http(401)

    assert "BRAPI_TOKEN" in str(erro)
    assert not getattr(erro, "recuperavel", False)


def test_rate_limit_e_recuperavel_e_erro_de_credencial_nao():
    p = provider()

    assert getattr(p._erro_http(429), "recuperavel", False) is True
    assert getattr(p._erro_http(500), "recuperavel", False) is True
    assert getattr(p._erro_http(403), "recuperavel", False) is False


def test_nao_repete_erro_definitivo():
    """Retentar credencial invalida so castiga a API de terceiro."""
    tentativas = []

    def abrir(url, cabecalhos):
        tentativas.append(url)
        raise BrapiError("brapi recusou a credencial (HTTP 401)")

    p = BrapiMarketDataProvider(config_brapi(), abrir=abrir, relogio=lambda: AGORA)
    with pytest.raises(BrapiError):
        p.cotacao("PETR4")

    assert len(tentativas) == 1


def test_erro_recuperavel_e_repetido_ate_o_limite(monkeypatch):
    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)
    tentativas = []

    def abrir(url, cabecalhos):
        tentativas.append(url)
        erro = BrapiError("brapi respondeu 429")
        erro.recuperavel = True
        raise erro

    p = BrapiMarketDataProvider(config_brapi(), abrir=abrir, relogio=lambda: AGORA)
    with pytest.raises(BrapiError):
        p.cotacao("PETR4")

    assert len(tentativas) == 3   # nao vira laco infinito


# --- simbolos -----------------------------------------------------------------------


def test_sem_token_a_lista_de_ativos_e_a_de_teste():
    assert provider(brapi_token="").simbolos() == ("PETR4", "VALE3", "MGLU3", "ITUB4")


def test_com_token_o_provedor_nao_afirma_uma_lista():
    assert provider().simbolos() == ()
