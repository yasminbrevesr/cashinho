"""As sondas: uma por componente."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.noticias import AvaliadorDeEventos, FonteArquivo, SemFonte
from cashinho.core.saude import (
    EstadoDeSaude,
    LimiaresSaude,
    SondaBanco,
    SondaBroker,
    SondaMarketData,
    SondaNoticias,
    SondaPorTelemetria,
    SondaRisco,
    Telemetria,
)
from cashinho.models import BRT

from .factories import AGORA, paper, risco, telemetria

SEXTA_FECHAMENTO = datetime(2026, 8, 21, 17, 55, tzinfo=BRT)


def market_data(dado_em=None, agora=AGORA, **anotacoes):
    t = Telemetria(relogio=lambda: agora)
    if dado_em is not None:
        t.sucesso("market_data", dado_em=dado_em, **anotacoes)
    return SondaMarketData(t).verificar(agora)


# --- Market Data: o componente critico -------------------------------------


def test_market_data_e_o_unico_critico():
    assert SondaMarketData().critico is True
    assert SondaPorTelemetria("scanner").critico is False


def test_dado_fresco_e_online():
    c = market_data(AGORA - timedelta(minutes=1))

    assert c.estado is EstadoDeSaude.ONLINE
    assert c.ultimo_timestamp == AGORA - timedelta(minutes=1)


def test_atraso_pequeno_e_degradado():
    assert market_data(AGORA - timedelta(minutes=5)).estado is EstadoDeSaude.DEGRADED


def test_atraso_grande_e_offline_e_nao_apenas_degradado():
    """Operar com candle velho e' pior que nao operar."""
    c = market_data(AGORA - timedelta(minutes=25))

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "nao serve para decidir" in c.detalhe


def test_sem_dado_nenhum_e_offline():
    c = market_data(None)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "nao esta vendo o mercado" in c.detalhe


def test_fora_do_pregao_o_relogio_de_parede_nao_conta():
    """As 15h de domingo, o candle das 17h55 de sexta esta em dia."""
    domingo = datetime(2026, 8, 23, 15, 0, tzinfo=BRT)

    assert market_data(SEXTA_FECHAMENTO, agora=domingo).estado is EstadoDeSaude.ONLINE


def test_mas_dado_de_semanas_atras_nao_fica_em_dia_so_porque_e_domingo():
    domingo = datetime(2026, 8, 23, 15, 0, tzinfo=BRT)
    antigo = SEXTA_FECHAMENTO - timedelta(days=21)

    assert market_data(antigo, agora=domingo).estado is EstadoDeSaude.OFFLINE


def test_no_pregao_seguinte_o_dado_da_sexta_esta_velho():
    segunda = datetime(2026, 8, 24, 11, 0, tzinfo=BRT)

    assert market_data(SEXTA_FECHAMENTO, agora=segunda).estado is EstadoDeSaude.OFFLINE


def test_latencia_alta_degrada_mesmo_com_dado_fresco():
    c = market_data(AGORA - timedelta(minutes=1), latencia_ms=3_000)

    assert c.estado is EstadoDeSaude.DEGRADED


def test_erros_recentes_degradam():
    t = Telemetria(relogio=lambda: AGORA)
    t.sucesso("market_data", dado_em=AGORA - timedelta(minutes=1))
    t.erro("market_data", "timeout")

    c = SondaMarketData(t).verificar(AGORA)

    assert c.estado is EstadoDeSaude.DEGRADED
    assert c.n_erros == 1


def test_muitos_erros_derrubam():
    t = Telemetria(relogio=lambda: AGORA)
    t.sucesso("market_data", dado_em=AGORA - timedelta(minutes=1))
    for i in range(6):
        t.erro("market_data", f"timeout {i}")

    assert SondaMarketData(t).verificar(AGORA).estado is EstadoDeSaude.OFFLINE


def test_os_limiares_sao_configuraveis():
    t = Telemetria(relogio=lambda: AGORA)
    t.sucesso("market_data", dado_em=AGORA - timedelta(minutes=5))

    frouxo = SondaMarketData(t, LimiaresSaude(market_data_degradado_min=10,
                                              market_data_offline_min=30))
    assert frouxo.verificar(AGORA).estado is EstadoDeSaude.ONLINE

    rigoroso = SondaMarketData(t, LimiaresSaude(market_data_degradado_min=1,
                                                market_data_offline_min=3))
    assert rigoroso.verificar(AGORA).estado is EstadoDeSaude.OFFLINE


# --- sonda por telemetria ------------------------------------------------------


def test_silencio_nao_vira_online():
    """Componente que nunca deu sinal de vida nao esta saudavel."""
    c = SondaPorTelemetria("scanner", Telemetria(relogio=lambda: AGORA)).verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "nunca reportou" in c.detalhe


def test_componente_opcional_sem_uso_fica_degradado():
    c = SondaPorTelemetria("backtest", Telemetria(relogio=lambda: AGORA),
                           opcional=True).verificar(AGORA)

    assert c.estado is EstadoDeSaude.DEGRADED
    assert "nunca usado" in c.detalhe


def test_atividade_recente_e_online():
    t = telemetria(AGORA, scanner=0)
    c = SondaPorTelemetria("scanner", t).verificar(AGORA)

    assert c.estado is EstadoDeSaude.ONLINE


def test_silencio_longo_derruba():
    momento = AGORA - timedelta(hours=5)
    t = Telemetria(relogio=lambda: momento)
    t.sucesso("scanner")

    assert SondaPorTelemetria("scanner", t).verificar(AGORA).estado is EstadoDeSaude.OFFLINE


# --- Database -----------------------------------------------------------------------


def test_banco_com_registros_e_online(tmp_path):
    caminho = tmp_path / "diario.jsonl"
    caminho.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")

    c = SondaBanco(caminho).verificar(AGORA)

    assert c.estado is EstadoDeSaude.ONLINE
    assert "2 registro(s)" in c.detalhe


def test_banco_sem_arquivo_ainda_e_degradado(tmp_path):
    c = SondaBanco(tmp_path / "diario.jsonl").verificar(AGORA)

    assert c.estado is EstadoDeSaude.DEGRADED
    assert "ainda nao existe" in c.detalhe


def test_pasta_inexistente_derruba_o_banco(tmp_path):
    c = SondaBanco(tmp_path / "sumida" / "diario.jsonl").verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "nada seria gravado" in c.detalhe


def test_pasta_sem_escrita_derruba_o_banco(tmp_path):
    import os
    import stat

    pasta = tmp_path / "somente-leitura"
    pasta.mkdir()
    os.chmod(pasta, stat.S_IRUSR | stat.S_IXUSR)
    try:
        c = SondaBanco(pasta / "diario.jsonl").verificar(AGORA)
        if os.access(pasta, os.W_OK):  # root ignora permissao
            pytest.skip("o usuario atual escreve mesmo sem permissao")
        assert c.estado is EstadoDeSaude.OFFLINE
        assert "nao seriam registradas" in c.detalhe
    finally:
        os.chmod(pasta, stat.S_IRWXU)


# --- Paper Broker --------------------------------------------------------------------


def test_broker_conectado_mostra_patrimonio_e_modo():
    c = SondaBroker(paper()).verificar(AGORA)

    assert c.estado is EstadoDeSaude.ONLINE
    assert c.modo == "simulado"
    assert "patrimonio" in c.detalhe


def test_sem_broker_o_componente_fica_offline():
    c = SondaBroker(None).verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "nenhum broker" in c.detalhe


def test_broker_que_explode_nao_derruba_o_painel():
    class Quebrado:
        simulado = True

        def get_balance(self):
            raise RuntimeError("conexao perdida")

    c = SondaBroker(Quebrado()).verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "conexao perdida" in c.detalhe


# --- Risk Manager ---------------------------------------------------------------------


def test_risco_liberado_e_online():
    c = SondaRisco(risco()).verificar(AGORA)

    assert c.estado is EstadoDeSaude.ONLINE
    assert c.modo == "TRADING LIBERADO"


def test_kill_switch_derruba_o_risco():
    r = risco()
    r.acionar_kill_switch("teste")

    c = SondaRisco(r).verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "KILL SWITCH" in c.detalhe


def test_risco_bloqueado_sem_kill_switch_e_degradado():
    r = risco(max_trades_dia=1, perda_max_diaria_pct=1.0)
    r.estado.pnl_dia = -5_000.0  # estourou a perda do dia

    c = SondaRisco(r).verificar(AGORA)

    assert c.estado is EstadoDeSaude.DEGRADED
    assert c.modo == "TRADING BLOQUEADO"


# --- News ---------------------------------------------------------------------------------


def test_sem_agenda_o_news_fica_offline():
    c = SondaNoticias(None).verificar(AGORA)

    assert c.estado is EstadoDeSaude.OFFLINE
    assert "NOTICIAS INDISPONIVEIS" in c.detalhe


def test_agenda_indisponivel_degrada_o_news():
    c = SondaNoticias(AvaliadorDeEventos(SemFonte())).verificar(AGORA)

    assert c.estado is EstadoDeSaude.DEGRADED
    assert "NOTICIAS INDISPONIVEIS" in c.detalhe


def test_agenda_fresca_deixa_o_news_online(tmp_path):
    import json

    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({
        "atualizado_em": AGORA.isoformat(), "fonte": "manual", "eventos": [],
    }), encoding="utf-8")

    c = SondaNoticias(AvaliadorDeEventos(FonteArquivo(caminho))).verificar(AGORA)

    assert c.estado is EstadoDeSaude.ONLINE
    assert "0 evento(s)" in c.detalhe
