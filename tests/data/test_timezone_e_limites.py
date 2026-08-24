"""Fuso, cache, freio de requisicoes e a tela de analise."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cashinho.data.cotacao import Cotacao, cotacao_indisponivel
from cashinho.data.mercado import MARGEM_COTACAO_S, limite_de_stale
from cashinho.data.rate_limit import Freio
from cashinho.data.servico import Finalidade
from cashinho.data.status import Capacidades, StatusDados
from cashinho.data.view import faixa_de_status, pagina_analise, secao_providers
from cashinho.models import BRT

from .factories import AGORA, ProviderFalso, provider_tempo_real, serie


# --- fuso: a regra e' uma so -----------------------------------------------


def test_cotacao_sem_fuso_e_recusada():
    """O Cashinho nao mistura horario ingenuo com horario com fuso."""
    with pytest.raises(ValueError, match="sem fuso"):
        Cotacao(symbol="PETR4", timestamp=datetime(2026, 8, 21, 14, 0),
                source="x", status=StatusDados.ONLINE)


def test_classificar_recusa_timestamp_ingenuo():
    p = ProviderFalso()

    with pytest.raises(ValueError, match="sem fuso"):
        p.classificar(datetime(2026, 8, 21, 14, 0), "1d", AGORA)


def test_utc_e_brasilia_sao_o_mesmo_instante():
    """Guardar em UTC ou em BRT nao pode mudar a idade do dado."""
    p = ProviderFalso(capacidades=Capacidades(candles_historicos=True))
    em_brt = AGORA - timedelta(minutes=30)
    em_utc = em_brt.astimezone(timezone.utc)

    assert p.classificar(em_brt, "5m", AGORA) is p.classificar(em_utc, "5m", AGORA)


def test_a_brapi_converte_epoch_para_brasilia():
    from cashinho.data.brapi import _momento

    convertido = _momento(int(AGORA.timestamp()))

    assert convertido.tzinfo is not None
    assert convertido == AGORA


def test_a_brapi_converte_iso_com_z_para_brasilia():
    from cashinho.data.brapi import _momento

    convertido = _momento("2026-08-21T17:00:00Z")

    assert convertido.utcoffset().total_seconds() == -3 * 3600
    assert convertido.hour == 14


# --- limite de "parado" varia por timeframe --------------------------------------


def test_o_limite_de_stale_cresce_com_o_timeframe():
    assert limite_de_stale("1m") < limite_de_stale("15m") < limite_de_stale("60m")


def test_o_diario_conta_em_dias_e_nao_em_horas_de_pregao():
    """Na segunda, o ultimo candle fechado e' o de sexta: nao e' parada."""
    assert limite_de_stale("1d") > 3 * 24 * 3600


def test_provedor_com_atraso_declarado_nunca_sai_online():
    p = ProviderFalso(capacidades=Capacidades(
        candles_historicos=True, atraso_tipico_s=900))

    assert p.classificar(AGORA - timedelta(minutes=5), "5m", AGORA) is StatusDados.DELAYED


def test_alem_do_atraso_prometido_vira_stale():
    p = ProviderFalso(capacidades=Capacidades(
        candles_historicos=True, atraso_tipico_s=900))

    assert p.classificar(AGORA - timedelta(hours=8), "5m", AGORA) is StatusDados.STALE


def test_a_cotacao_tem_regua_propria():
    """Candle diario de ontem esta em dia; cotacao de ontem, nao."""
    p = ProviderFalso(capacidades=Capacidades(cotacao=True, atraso_tipico_s=None))

    assert p.classificar_cotacao(AGORA - timedelta(seconds=10), AGORA) is StatusDados.ONLINE
    assert p.classificar_cotacao(AGORA - timedelta(hours=20), AGORA) is StatusDados.STALE


# --- freio de requisicoes -------------------------------------------------------------


def test_sem_teto_configurado_nao_ha_freio():
    freio = Freio(None)

    assert freio.ativo is False
    assert freio.aguardar() == 0.0


def test_dentro_do_teto_nao_espera():
    tempo = [0.0]
    freio = Freio(3, relogio=lambda: tempo[0], dormir=lambda s: None)

    assert [freio.aguardar() for _ in range(3)] == [0.0, 0.0, 0.0]


def test_estourar_o_teto_faz_esperar():
    tempo = [0.0]
    dormidas = []

    def dormir(s):
        dormidas.append(s)
        tempo[0] += s

    freio = Freio(2, relogio=lambda: tempo[0], dormir=dormir)
    freio.aguardar(); freio.aguardar()
    freio.aguardar()   # o terceiro estoura

    assert dormidas and dormidas[0] > 0
    assert freio.esperas == 1


def test_a_janela_desliza():
    tempo = [0.0]
    freio = Freio(2, relogio=lambda: tempo[0], dormir=lambda s: None)
    freio.aguardar(); freio.aguardar()
    tempo[0] = 61.0   # passou a janela

    assert freio.aguardar() == 0.0


# --- cache nao pode fazer dado vencido parecer novo -------------------------------------


def test_o_cache_guarda_e_devolve_a_serie(tmp_path):
    from cashinho.data.cache import Cache

    cache = Cache(pasta=tmp_path, ttl_segundos=60)
    s = serie(n=5, timeframe="1d")
    cache.guardar("PETR4-1d", s)

    devolvida = cache.obter("PETR4-1d")
    assert devolvida is not None and len(devolvida) == 5


def test_o_cache_vencido_nao_devolve_dado_velho_como_novo(tmp_path):
    import time

    from cashinho.data.cache import Cache

    cache = Cache(pasta=tmp_path, ttl_segundos=0)
    cache.guardar("PETR4-1m", serie(n=5, timeframe="1m"))
    time.sleep(0.01)

    assert cache.obter("PETR4-1m") is None


# --- a tela mostra origem, estado e o aviso ------------------------------------------------


def leitura(status=StatusDados.DELAYED, finalidade=Finalidade.HISTORICO):
    from cashinho.data.qualidade import ValidadorDeQualidade
    from cashinho.data.servico import Leitura

    s = serie(n=10, timeframe="1d")
    q = ValidadorDeQualidade(relogio=lambda: AGORA).validar(s)
    return Leitura(s, "brapi", status, finalidade, q, AGORA)


def test_a_tela_mostra_fonte_status_e_qualidade():
    texto = pagina_analise(leitura())

    assert "brapi" in texto
    assert "DELAYED" in texto
    assert "QUALIDADE DOS DADOS" in texto


def test_dado_atrasado_leva_faixa_de_aviso():
    texto = pagina_analise(leitura(StatusDados.DELAYED))

    assert "NAO UTILIZAR PARA ENTRADA EM TEMPO REAL" in texto


def test_dado_online_nao_leva_faixa():
    assert faixa_de_status(StatusDados.ONLINE) == ""


def test_a_tela_nunca_chama_dado_atrasado_de_tempo_real():
    texto = pagina_analise(leitura(StatusDados.DELAYED)).upper()

    assert "COTACAO EM TEMPO REAL" not in texto


def test_finalidade_de_tempo_real_com_dado_atrasado_e_reprovada():
    texto = pagina_analise(leitura(StatusDados.DELAYED, Finalidade.SCANNER_INTRADIARIO))

    assert "NAO usar para" in texto


def test_a_secao_de_providers_mostra_os_dois_papeis():
    from cashinho.data.servico import MarketDataService

    s = MarketDataService(historico=ProviderFalso("brapi"),
                          tempo_real=provider_tempo_real())
    texto = secao_providers(s)

    assert "Historical Provider" in texto and "brapi" in texto
    assert "Realtime Provider" in texto and "mt5" in texto
    assert "DISPONIVEL" in texto


def test_sem_realtime_a_secao_avisa_que_esta_bloqueado():
    from cashinho.data.servico import MarketDataService

    texto = secao_providers(MarketDataService(historico=ProviderFalso("brapi")))

    assert "NAO CONFIGURADO" in texto
    assert "INDISPONIVEL" in texto
    assert "bloqueadas" in texto


def test_cotacao_indisponivel_nao_traz_numero():
    c = cotacao_indisponivel("PETR4", "brapi", "feed caiu", AGORA)

    assert c.last is None and c.status is StatusDados.OFFLINE
    assert "feed caiu" in c.detalhe
