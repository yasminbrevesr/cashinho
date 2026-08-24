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


def test_a_cotacao_usa_o_endpoint_v2():
    registro = []
    provider(registro=registro).cotacao("PETR4")

    url, _ = registro[0]
    assert url == "https://brapi.dev/api/v2/stocks/quote?symbols=PETR4"


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


def test_o_historico_continua_no_endpoint_de_quote_com_range():
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


def test_erro_recuperavel_e_repetido_ate_o_limite():
    tentativas = []

    def abrir(url, cabecalhos):
        tentativas.append(url)
        erro = BrapiError("brapi respondeu 429")
        erro.recuperavel = True
        raise erro

    p = BrapiMarketDataProvider(config_brapi(), abrir=abrir, relogio=lambda: AGORA,
                                dormir=lambda s: None)
    with pytest.raises(BrapiError):
        p.cotacao("PETR4")

    assert len(tentativas) == 3   # nao vira laco infinito


# --- simbolos -----------------------------------------------------------------------


def test_sem_token_a_lista_de_ativos_e_a_de_teste():
    assert provider(brapi_token="").simbolos() == ("PETR4", "VALE3", "MGLU3", "ITUB4")


def test_com_token_o_provedor_nao_afirma_uma_lista():
    assert provider().simbolos() == ()


# ---------------------------------------------------------------------------
# endpoint v2: GET /api/v2/stocks/quote?symbols=... -> results[0].data
# ---------------------------------------------------------------------------


from .factories import resposta_v2   # noqa: E402


def v2(corpo=None, registro=None, codigo: int = 200, **campos):
    from cashinho.data.brapi import BrapiMarketDataProvider

    return BrapiMarketDataProvider(
        config_brapi(**campos),
        abrir=abridor(corpo if corpo is not None else resposta_v2(), registro, codigo),
        relogio=lambda: AGORA,
        dormir=lambda s: None,   # retentativa sem espera de verdade
    )


def test_a_url_e_exatamente_a_do_contrato():
    registro = []
    v2(registro=registro).buscar_cotacao("B3SA3")

    url, _ = registro[0]
    assert url == "https://brapi.dev/api/v2/stocks/quote?symbols=B3SA3"


def test_o_simbolo_e_normalizado_para_maiusculo():
    registro = []
    v2(registro=registro).buscar_cotacao("b3sa3")

    assert "symbols=B3SA3" in registro[0][0]


def test_devolve_o_conteudo_de_results_zero_data():
    """A v2 aninha os campos em data; a funcao entrega o payload de dentro."""
    dados = v2().buscar_cotacao("PETR4")

    assert dados["symbol"] == "PETR4"
    assert dados["regularMarketPrice"] == 38.42
    assert "data" not in dados        # ja veio desembrulhado


def test_a_rota_antiga_sem_data_continua_funcionando():
    """results[0] direto, sem 'data': aceito, para uma troca de rota nao
    virar campo faltando la na frente."""
    dados = v2(resposta_brapi()).buscar_cotacao("PETR4")

    assert dados["regularMarketPrice"] == 38.42


def test_a_cotacao_normalizada_sai_do_payload_da_v2():
    cot = v2().cotacao("PETR4")

    assert cot.last == 38.42
    assert cot.source == "brapi"
    assert cot.status is StatusDados.DELAYED


def test_o_token_vai_no_cabecalho_e_nunca_na_url_da_v2():
    registro = []
    v2(registro=registro).buscar_cotacao("PETR4")

    url, cabecalhos = registro[0]
    assert cabecalhos["Authorization"] == "Bearer token-de-teste"
    assert "token" not in url.lower()


# --- respostas nao-2xx ------------------------------------------------------


@pytest.mark.parametrize("codigo,trecho", [
    (400, "HTTP 400"),
    (401, "credencial"),
    (403, "credencial"),
    (404, "nao encontrado"),
    (429, "limite de requisicoes"),
    (500, "erro interno"),
    (503, "erro interno"),
])
def test_resposta_nao_2xx_vira_erro_explicado(codigo, trecho):
    with pytest.raises(BrapiError, match=trecho):
        v2(json.dumps({"message": "ops"}), codigo=codigo).buscar_cotacao("PETR4")


def test_o_erro_carrega_a_explicacao_da_propria_api():
    with pytest.raises(BrapiError, match="token invalido"):
        v2(json.dumps({"message": "token invalido"}), codigo=401).buscar_cotacao("PETR4")


def test_corpo_de_erro_que_nao_e_json_ainda_aparece():
    with pytest.raises(BrapiError, match="manutencao"):
        v2("<html>manutencao</html>", codigo=500).buscar_cotacao("PETR4")


def test_401_diz_onde_conferir_o_token():
    with pytest.raises(BrapiError, match="BRAPI_TOKEN no .env"):
        v2("{}", codigo=401).buscar_cotacao("PETR4")


def test_429_aponta_a_configuracao_do_freio():
    with pytest.raises(BrapiError, match="BRAPI_REQUISICOES_POR_MINUTO"):
        v2("{}", codigo=429).buscar_cotacao("PETR4")


def test_2xx_diferente_de_200_e_aceito():
    p = v2(resposta_v2(), codigo=204)
    # 204 sem corpo valido cai no erro de JSON, nao no de status
    with pytest.raises(BrapiError):
        v2("", codigo=204).buscar_cotacao("PETR4")
    assert p.buscar_cotacao("PETR4")["symbol"] == "PETR4"


# --- respostas 2xx malformadas ------------------------------------------------


def test_results_vazio_vira_erro():
    with pytest.raises(BrapiError, match="sem resultado"):
        v2(json.dumps({"results": []})).buscar_cotacao("PETR4")


def test_sem_a_chave_results_vira_erro():
    with pytest.raises(BrapiError, match="sem resultado"):
        v2(json.dumps({"erro": "nada"})).buscar_cotacao("PETR4")


def test_results_zero_em_formato_inesperado_vira_erro():
    with pytest.raises(BrapiError, match="formato inesperado"):
        v2(json.dumps({"results": ["so um texto"]})).buscar_cotacao("PETR4")


def test_corpo_2xx_que_nao_e_json_vira_erro():
    with pytest.raises(BrapiError, match="nao e' JSON"):
        v2("<html>").buscar_cotacao("PETR4")


# ---------------------------------------------------------------------------
# a credencial nao vaza
# ---------------------------------------------------------------------------


def test_o_token_nunca_aparece_no_payload_da_configuracao():
    """para_dict vai para tela, JSON e log: token ali seria vazamento."""
    from cashinho.settings import ConfigMarketData

    cfg = ConfigMarketData(brapi_token="segredo-que-nao-pode-vazar")

    assert "segredo" not in json.dumps(cfg.para_dict())
    assert cfg.para_dict()["brapi_autenticado"] is True


def test_o_token_nunca_aparece_no_payload_do_provedor():
    p = v2(brapi_token="segredo-que-nao-pode-vazar")

    assert "segredo" not in json.dumps(p.para_dict())


def test_o_token_nao_entra_na_mensagem_de_erro():
    p = v2(json.dumps({"message": "sem permissao"}), codigo=401,
           brapi_token="segredo-que-nao-pode-vazar")

    with pytest.raises(BrapiError) as e:
        p.buscar_cotacao("PETR4")
    assert "segredo" not in str(e.value)


def test_a_chave_de_verdade_nao_esta_versionada():
    """O .env fica de fora do repositorio; so o .env.example e' versionado."""
    import pathlib
    import subprocess

    raiz = pathlib.Path(__file__).resolve().parents[2]
    rastreados = subprocess.run(
        ["git", "ls-files"], cwd=raiz, capture_output=True, text=True).stdout.split()

    assert ".env" not in rastreados
    assert ".env.example" in rastreados
