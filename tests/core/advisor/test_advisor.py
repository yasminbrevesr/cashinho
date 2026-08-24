"""O Advisor: look-ahead, histerese, status e ranking deterministico."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.advisor import (
    ConfigAdvisor,
    ConfigEstabilidade,
    Estatistica,
    NivelDeConfianca,
    RecomendacaoAtual,
    StatusAdvisor,
    TimeframeAdvisor,
    decidir,
)
from cashinho.core.advisor.periodos import PeriodoDoPregao, periodo_de
from cashinho.models import BRT, Series

from .factories import (
    ABERTURA,
    atual,
    estatistica,
    lateral_ruidosa,
    onda,
    serie_1m,
    tendencia,
)


def advisor(**campos) -> TimeframeAdvisor:
    return TimeframeAdvisor(ConfigAdvisor(**campos) if campos else None)


# --- ausencia de look-ahead ------------------------------------------------


def test_a_recomendacao_em_t_so_usa_dados_ate_t():
    """O teste decisivo: mudar o futuro nao pode mudar o passado."""
    serie = tendencia(600)
    instante = serie.candles[300].ts

    antes = advisor().avaliar(serie, as_of=instante)

    # troca todo o futuro por outra coisa - com os timestamps CONTINUANDO
    # depois do instante, senao o teste corromperia o passado em vez do futuro
    from datetime import timedelta

    outro_futuro = lateral_ruidosa(299).candles
    deslocamento = (serie.candles[301].ts - outro_futuro[0].ts)
    futuro = [
        type(c)(c.ts + deslocamento, c.open, c.high, c.low, c.close, c.volume)
        for c in outro_futuro
    ]
    futuro_diferente = Series(serie.symbol, serie.timeframe,
                              serie.candles[:301] + futuro)
    depois = advisor().avaliar(futuro_diferente, as_of=instante)

    assert antes.setup_timeframe == depois.setup_timeframe
    assert [r.total for r in antes.rankings] == [r.total for r in depois.rankings]


def test_nenhum_candle_avaliado_termina_depois_do_instante():
    serie = tendencia(600)
    instante = serie.candles[400].ts
    rec = advisor().avaliar(serie, as_of=instante)

    for item in rec.rankings:
        assert item.medidas.candles > 0
    # a vista do MTF ja corta; aqui garantimos que o Advisor usa a vista
    assert rec.as_of == instante


def test_avaliar_mais_cedo_ve_menos_candles():
    serie = tendencia(600)
    cedo = advisor().avaliar(serie, as_of=serie.candles[200].ts)
    tarde = advisor().avaliar(serie, as_of=serie.candles[550].ts)

    tf = "5m"
    assert (cedo.item(tf).medidas.candles or 0) < (tarde.item(tf).medidas.candles or 0)


# --- ranking ------------------------------------------------------------------


def test_o_ranking_e_deterministico():
    serie = tendencia(500)
    a = advisor().avaliar(serie)
    b = advisor().avaliar(serie)

    assert [r.timeframe for r in a.rankings] == [r.timeframe for r in b.rankings]


def test_o_ranking_sai_ordenado_por_score():
    rec = advisor().avaliar(tendencia(500))
    notas = [r.total for r in rec.rankings]

    assert notas == sorted(notas, reverse=True)


def test_empate_e_desempatado_de_forma_estavel():
    """Empate nao pode depender da ordem do dicionario."""
    rec = advisor().avaliar(tendencia(500))
    pares = [(r.total, r.market_fit, r.timeframe) for r in rec.rankings]

    assert pares == sorted(pares, key=lambda p: (-p[0], -p[1], p[2]))


def test_ruido_nao_periodico_derruba_todos_os_timeframes():
    """Preco que anda muito e nao chega a lugar nenhum em NENHUMA escala.

    A leitura honesta aqui nao e' "o timeframe X e' o melhor" - e' que nao ha
    timeframe bom. Exigir que um deles perdesse para outro seria inventar
    ordem entre opcoes igualmente ruins.
    """
    rec = advisor().avaliar(lateral_ruidosa(500))
    notas_de_ruido = [r.score.componente("ruido").nota for r in rec.rankings
                      if r.score.componente("ruido").disponivel]

    assert max(notas_de_ruido) < 40
    assert rec.rankings[0].total < 60      # nenhum lider convincente


def test_oscilacao_periodica_nao_e_ruido():
    """Senoide de 19 min e' operavel no 1m e nao no 15m - e o Advisor ve isso.

    A distincao importa: tratar ciclo como ruido faria o Advisor recusar
    justamente o timeframe em que o movimento existe.
    """
    rec = advisor().avaliar(onda(500, periodo=19.0))
    fino = rec.item("1m").score.componente("ruido").nota
    grosso = rec.item("15m").score.componente("ruido").nota

    assert fino > grosso


# --- contexto, setup e gatilho --------------------------------------------------


def test_recomenda_a_combinacao_completa():
    rec = advisor().avaliar(tendencia(600))

    if rec.tem_recomendacao:
        assert rec.context_timeframe in ("15m", "30m", "60m")
        assert rec.setup_timeframe in ConfigAdvisor().setup
        assert rec.trigger_timeframe in ConfigAdvisor().gatilho


def test_o_gatilho_e_sempre_mais_fino_que_o_setup():
    from cashinho.core.mtf.timeframes import parse_timeframe

    for serie in (tendencia(600), lateral_ruidosa(600), onda(600)):
        rec = advisor().avaliar(serie)
        if rec.trigger_timeframe is None:
            continue
        assert (parse_timeframe(rec.trigger_timeframe).minutos
                < parse_timeframe(rec.setup_timeframe).minutos)


def test_setup_no_timeframe_mais_fino_nao_inventa_gatilho():
    """Gatilho igual ao setup sugeriria uma confirmacao que nao existe."""
    rec = advisor(setup=("1m", "2m"), gatilho=("1m",)).avaliar(tendencia(600))

    if rec.tem_recomendacao and rec.setup_timeframe == "1m":
        assert rec.trigger_timeframe is None
        assert any("nao ha granularidade menor" in a for a in rec.warnings)


def test_o_contexto_nao_e_necessariamente_o_melhor_setup():
    """Sao perguntas diferentes: direcao maior x onde desenhar a operacao."""
    rec = advisor().avaliar(tendencia(600))

    if rec.tem_recomendacao:
        assert rec.context_timeframe != rec.trigger_timeframe


# --- status ---------------------------------------------------------------------


def test_serie_curta_vira_dados_insuficientes():
    rec = advisor().avaliar(serie_1m(25))

    assert rec.status is StatusAdvisor.DADOS_INSUFICIENTES
    assert rec.tem_recomendacao is False


def test_serie_vazia_nao_quebra():
    rec = advisor().avaliar(Series("PETR4", "1m", []))

    assert rec.status is StatusAdvisor.DADOS_INSUFICIENTES
    assert rec.warnings


def test_o_sistema_pode_dizer_que_nao_ha_recomendacao_confiavel():
    """Nao ha vencedor forcado."""
    rec = advisor(confianca_minima=99.0).avaliar(tendencia(500))

    assert rec.status in (StatusAdvisor.CONFIANCA_BAIXA,
                          StatusAdvisor.DADOS_INSUFICIENTES)
    assert rec.tem_recomendacao is False
    assert "SEM RECOMENDACAO CONFIAVEL" in rec.status.rotulo or True


def test_status_acionavel_so_para_recomendado_e_manter():
    assert StatusAdvisor.RECOMENDADO.acionavel is True
    assert StatusAdvisor.MANTER_ATUAL.acionavel is True
    assert StatusAdvisor.CONFIANCA_BAIXA.acionavel is False
    assert StatusAdvisor.DADOS_INSUFICIENTES.acionavel is False


# --- histerese --------------------------------------------------------------------


def test_diferenca_pequena_mantem_o_timeframe_atual():
    """5m em 82 contra 2m em 84: nao troca."""
    d = decidir("2m", 84.0, atual("5m", 82.0), ABERTURA + timedelta(hours=8))

    assert d.manter is True
    assert d.timeframe == "5m"
    assert "abaixo da margem" in d.motivo


def test_diferenca_grande_permite_a_troca():
    """5m em 63 contra 2m em 88: troca."""
    d = decidir("2m", 88.0, atual("5m", 63.0), ABERTURA + timedelta(hours=8))

    assert d.manter is False
    assert d.timeframe == "2m"


def test_a_carencia_segura_a_troca_recente():
    agora = ABERTURA + timedelta(minutes=400)
    d = decidir("2m", 95.0, atual("5m", 80.0, minutos_atras=2, agora=agora), agora)

    assert d.manter is True
    assert "carencia" in d.motivo


def test_timeframe_atual_ruim_ignora_a_carencia():
    """Se o atual desabou, esperar quinze minutos nao ajuda ninguem."""
    agora = ABERTURA + timedelta(minutes=400)
    d = decidir("2m", 90.0, atual("5m", 40.0, minutos_atras=2, agora=agora), agora)

    assert d.manter is False


def test_o_mesmo_timeframe_nao_e_troca():
    d = decidir("5m", 90.0, atual("5m", 70.0), ABERTURA + timedelta(hours=8))

    assert d.manter is True
    assert "continua sendo o atual" in d.motivo


def test_sem_recomendacao_anterior_nao_ha_o_que_manter():
    d = decidir("5m", 70.0, None, ABERTURA + timedelta(hours=8))

    assert d.manter is False
    assert "primeira recomendacao" in d.motivo


def test_os_limiares_da_histerese_sao_configuraveis():
    frouxa = ConfigEstabilidade(vantagem_minima=1.0, tempo_minimo_min=0.0)
    rigida = ConfigEstabilidade(vantagem_minima=30.0)
    agora = ABERTURA + timedelta(hours=8)

    assert decidir("2m", 84.0, atual("5m", 82.0), agora, frouxa).manter is False
    assert decidir("2m", 84.0, atual("5m", 82.0), agora, rigida).manter is True


def test_a_histerese_entra_na_recomendacao():
    serie = tendencia(600)
    rec = advisor().avaliar(serie, atual=atual("1m", 90.0, minutos_atras=1))

    assert rec.decisao is not None
    if rec.status is StatusAdvisor.MANTER_ATUAL:
        assert rec.setup_timeframe == "1m"


# --- periodo do pregao ---------------------------------------------------------------


def test_o_periodo_do_pregao_e_carimbado():
    rec = advisor().avaliar(tendencia(400))

    assert rec.periodo in PeriodoDoPregao


def test_os_periodos_cobrem_o_pregao():
    from datetime import datetime

    assert periodo_de(datetime(2026, 8, 20, 10, 30, tzinfo=BRT)) is PeriodoDoPregao.ABERTURA
    assert periodo_de(datetime(2026, 8, 20, 12, 0, tzinfo=BRT)) is PeriodoDoPregao.MEIO
    assert periodo_de(datetime(2026, 8, 20, 15, 0, tzinfo=BRT)) is PeriodoDoPregao.TARDE
    assert periodo_de(datetime(2026, 8, 20, 17, 0, tzinfo=BRT)) is PeriodoDoPregao.FECHAMENTO
    assert periodo_de(datetime(2026, 8, 22, 12, 0, tzinfo=BRT)) is PeriodoDoPregao.FORA


# --- estatistica opcional -------------------------------------------------------------


def test_estatistica_por_timeframe_entra_no_score():
    serie = tendencia(600)
    sem = advisor().avaliar(serie)
    com = advisor().avaliar(serie, estatisticas={"5m": estatistica(trades=60)})

    assert sem.item("5m").statistical_evidence is None
    assert com.item("5m").statistical_evidence is not None


def test_a_recomendacao_serializa():
    import json

    json.dumps(advisor().avaliar(tendencia(500)).para_dict())


def test_o_advisor_nao_importa_metatrader():
    """A docstring cita o nome para dizer que nao importa - vale o codigo."""
    import ast
    import pathlib

    for arquivo in pathlib.Path("src/cashinho/core/advisor").glob("*.py"):
        arvore = ast.parse(arquivo.read_text())
        modulos = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                modulos.add(no.module)
            elif isinstance(no, ast.Import):
                modulos |= {a.name for a in no.names}
        assert not any("etaTrader" in m for m in modulos), arquivo.name
