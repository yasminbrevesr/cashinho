"""O servico que escolhe provedor por finalidade - e nunca faz fallback calado."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.data.base import DataError
from cashinho.data.fabrica import (
    IMPLEMENTADOS,
    PLANEJADOS,
    ProvedorDesconhecidoError,
    catalogo,
    construir,
    montar_servico,
)
from cashinho.data.servico import (
    Finalidade,
    MarketDataService,
    TempoRealIndisponivelError,
)
from cashinho.data.status import Capacidades, CapacidadeAusenteError, StatusDados
from cashinho.settings import ConfigMarketData

from .factories import AGORA, ProviderFalso, provider_tempo_real, serie


def servico(historico=None, tempo_real=None):
    return MarketDataService(
        historico=historico if historico is not None else ProviderFalso("historico"),
        tempo_real=tempo_real, relogio=lambda: AGORA)


# --- separacao por finalidade ------------------------------------------------


def test_backtest_usa_o_provedor_historico():
    s = servico()

    assert s.provedor(Finalidade.BACKTEST).nome == "historico"


def test_finalidades_de_tempo_real_estao_declaradas():
    assert Finalidade.SCANNER_INTRADIARIO.exige_tempo_real is True
    assert Finalidade.PAPER_AO_VIVO.exige_tempo_real is True
    assert Finalidade.ANALISE_ASSISTIDA.exige_tempo_real is True
    assert Finalidade.BACKTEST.exige_tempo_real is False
    assert Finalidade.PESQUISA.exige_tempo_real is False


def test_scanner_intradiario_usa_o_provedor_de_tempo_real():
    s = servico(tempo_real=provider_tempo_real())

    assert s.provedor(Finalidade.SCANNER_INTRADIARIO).nome == "mt5"


# --- a proibicao central: nada de fallback silencioso --------------------------


def test_sem_provedor_de_tempo_real_a_operacao_e_recusada():
    """Nunca cair para o historico fingindo que e' mercado."""
    s = servico(tempo_real=None)

    with pytest.raises(TempoRealIndisponivelError) as e:
        s.candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)

    assert "nao usa dado historico no lugar" in str(e.value)


def test_o_historico_continua_funcionando_sem_tempo_real():
    """A falta de tempo real bloqueia so o que precisa dele."""
    leitura = servico().candles("PETR4", "1d", 30, Finalidade.BACKTEST)

    assert leitura.utilizavel is True


def test_provedor_atrasado_nao_serve_para_tempo_real():
    atrasado = ProviderFalso("brapi", capacidades=Capacidades(
        candles_historicos=True, cotacao=True, intradiario_1m=True,
        timeframes=("1m",), atraso_tipico_s=900))
    s = servico(tempo_real=atrasado)

    with pytest.raises(CapacidadeAusenteError, match="nao serve para day trade"):
        s.candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)


def test_provedor_sem_1m_e_recusado_para_intradiario():
    sem_1m = ProviderFalso("x", capacidades=Capacidades(
        candles_historicos=True, cotacao_em_tempo_real=True,
        timeframes=("5m",), atraso_tipico_s=1))
    s = servico(tempo_real=sem_1m)

    with pytest.raises(CapacidadeAusenteError, match="1m"):
        s.candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)


def test_cotacao_atrasada_e_recusada_para_finalidade_de_tempo_real():
    from cashinho.data.cotacao import Cotacao

    atrasada = Cotacao(symbol="PETR4", timestamp=AGORA - timedelta(minutes=20),
                       source="brapi", status=StatusDados.DELAYED, last=38.0,
                       data_age=1200)
    p = provider_tempo_real(cotacao=atrasada)

    with pytest.raises(TempoRealIndisponivelError, match="DELAYED"):
        servico(tempo_real=p).cotacao("PETR4", Finalidade.PAPER_AO_VIVO)


# --- a leitura carrega origem, estado e qualidade -------------------------------


def test_a_leitura_diz_de_onde_veio_e_se_da_para_usar():
    leitura = servico().candles("PETR4", "1d", 30)

    assert leitura.fonte == "historico"
    assert leitura.qualidade.valida is True
    assert leitura.status in StatusDados
    assert "fonte" in str(leitura.para_dict()) or leitura.para_dict()["fonte"]


def test_dado_invalido_torna_a_leitura_inutilizavel():
    from cashinho.models import Series

    vazio = ProviderFalso("vazio", series=Series("PETR4", "1d", []))
    leitura = servico(historico=vazio).candles("PETR4", "1d", 30)

    assert leitura.utilizavel is False
    assert "DADOS INVALIDOS" in leitura.aviso


def test_erro_do_provedor_sobe_com_a_origem():
    quebrado = ProviderFalso("quebrado", erro="feed caiu")

    with pytest.raises(DataError, match="feed caiu"):
        servico(historico=quebrado).candles("PETR4", "1d", 30)


def test_sem_provedor_historico_a_leitura_e_recusada():
    with pytest.raises(DataError, match="nenhum provedor historico"):
        MarketDataService().candles("PETR4", "1d", 30)


# --- fabrica -------------------------------------------------------------------------


def test_o_catalogo_lista_os_providers_implementados():
    c = catalogo()

    assert c["brapi"]["disponivel"] is True
    assert c["metatrader"]["disponivel"] is True


def test_metatrader_e_construivel_mesmo_sem_a_biblioteca():
    """Em Linux/CI o provedor carrega; quem falha e' a conexao, com motivo."""
    p = construir("metatrader")

    assert p.nome == "metatrader"
    assert p.capacidades.trading is False


def test_sem_a_biblioteca_a_conexao_diz_o_que_falta():
    p = construir("metatrader")
    info = p.conectar()

    assert info.conectado is False
    assert "METATRADER NAO DISPONIVEL" in info.motivo


def test_provedor_desconhecido_lista_os_disponiveis():
    with pytest.raises(ProvedorDesconhecidoError, match="implementados"):
        construir("bloomberg")


def test_monta_o_servico_a_partir_da_configuracao():
    s = montar_servico(ConfigMarketData(historico="demo"))

    assert s.historico.nome == "demo"
    assert s.tem_tempo_real is False


def test_provedor_de_tempo_real_inexistente_falha_alto():
    """Nao vira historico disfarcado."""
    with pytest.raises(ProvedorDesconhecidoError):
        montar_servico(ConfigMarketData(historico="demo", tempo_real="bloomberg"))


def test_metatrader_pode_ocupar_o_papel_de_tempo_real():
    s = montar_servico(ConfigMarketData(historico="demo", tempo_real="metatrader"))

    assert s.tem_tempo_real is True
    assert s.tempo_real.nome == "metatrader"


def test_o_retrato_do_servico_diz_se_ha_analise_em_tempo_real():
    sem = montar_servico(ConfigMarketData(historico="demo")).para_dict()
    com = servico(tempo_real=provider_tempo_real()).para_dict()

    assert sem["analise_em_tempo_real"] == "INDISPONIVEL"
    assert com["analise_em_tempo_real"] == "DISPONIVEL"


# --- os provedores existentes declararam capacidades -----------------------------------


def test_os_provedores_existentes_declaram_capacidades(tmp_path):
    """Migrar para MarketDataProvider so vale se todos declararem o que fazem."""
    from cashinho.data.csv_provider import CSVProvider
    from cashinho.data.synthetic import SyntheticProvider

    assert SyntheticProvider().capacidades.candles_historicos is True
    assert CSVProvider.capacidades.candles_historicos is True

    try:
        from cashinho.data.yahoo import YahooProvider

        assert YahooProvider.capacidades.candles_historicos is True
        # o Yahoo publica intradiario, mas com atraso: nao serve para entrada
        assert YahooProvider.capacidades.serve_para_day_trade is False
    except DataError:
        pass   # yfinance ausente neste ambiente


def test_o_demo_nao_se_declara_apto_a_tempo_real():
    """Dado sintetico exercita o sistema; nunca decide."""
    assert construir("demo").capacidades.serve_para_day_trade is False
