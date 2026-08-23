"""O relatorio compara as tres particoes e grita quando o desempenho cai fora da amostra."""

from __future__ import annotations

import pytest

from cashinho.core.validacao import (
    Alerta,
    CofreDeTeste,
    CriteriosDeDegradacao,
    DivisaoDeDados,
    Medidas,
    Particao,
    RelatorioDeValidacao,
    Severidade,
)

from .factories import medidas, serie_de_dias


@pytest.fixture
def divisao():
    return DivisaoDeDados.por_percentual(serie_de_dias(dias=10))


def relatorio(divisao, treino=None, validacao=None, teste=None, cofre=None,
              criterios=None):
    ms = [m for m in (treino, validacao, teste) if m is not None]
    return RelatorioDeValidacao(divisao, ms, cofre=cofre, criterios=criterios)


def chaves(rel):
    return [a.chave for a in rel.alertas]


# --- as seis medidas pedidas -------------------------------------------------


def test_o_relatorio_traz_as_seis_medidas_por_particao(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN), medidas(Particao.VALIDATION),
                    medidas(Particao.TEST))
    dados = rel.para_dict()["medidas"]

    assert len(dados) == 3
    for m in dados:
        assert set(m) >= {"retorno_pct", "max_drawdown_pct", "profit_factor",
                          "sharpe", "expectancy", "n_trades"}


def test_medidas_saem_do_resultado_de_backtest():
    from cashinho.core.backtest.models import Metricas

    class R:
        metricas = Metricas(retorno_total_pct=3.0, max_drawdown_pct=1.0,
                            profit_factor=1.5, sharpe=0.9, expectancy=12.0,
                            n_trades=25)

    m = Medidas.de_resultado(Particao.TRAIN, R(), dias=8)
    assert (m.retorno_pct, m.n_trades, m.dias) == (3.0, 25, 8)


# --- sem degradacao ------------------------------------------------------------


def test_desempenho_que_se_manteve_nao_gera_critico(divisao):
    rel = relatorio(
        divisao,
        medidas(Particao.TRAIN, retorno=6.0, expectancy=60.0, trades=40),
        medidas(Particao.VALIDATION, retorno=5.0, expectancy=55.0, trades=25),
        medidas(Particao.TEST, retorno=4.5, expectancy=50.0, trades=25),
    )

    assert rel.degradou is False
    assert "se manteve" in rel.veredito


# --- os alertas de degradacao ----------------------------------------------------


def test_retorno_que_vira_negativo_fora_da_amostra_e_critico(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, retorno=8.0),
                    medidas(Particao.VALIDATION, retorno=-2.0))

    assert "retorno_virou_negativo" in chaves(rel)
    assert rel.degradou is True
    assert "nao se sustentaram" in rel.veredito


def test_queda_grande_de_retorno_vira_alerta(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, retorno=10.0),
                    medidas(Particao.VALIDATION, retorno=2.0))

    alerta = next(a for a in rel.alertas if a.chave == "retorno_caiu")
    assert alerta.severidade is Severidade.ALERTA
    assert "80%" in alerta.mensagem


def test_queda_pequena_de_retorno_nao_alerta(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, retorno=10.0),
                    medidas(Particao.VALIDATION, retorno=8.0))

    assert "retorno_caiu" not in chaves(rel)


def test_drawdown_muito_pior_fora_da_amostra_alerta(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, drawdown=2.0),
                    medidas(Particao.VALIDATION, drawdown=6.0))

    assert "drawdown_piorou" in chaves(rel)


def test_profit_factor_abaixo_de_um_fora_da_amostra_e_critico(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, pf=2.0),
                    medidas(Particao.VALIDATION, pf=0.7))

    assert "profit_factor_abaixo_de_um" in chaves(rel)
    assert rel.degradou is True


def test_expectancy_negativa_fora_da_amostra_e_critica(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, expectancy=80.0),
                    medidas(Particao.VALIDATION, expectancy=-5.0))

    assert "expectancy_virou_negativa" in chaves(rel)


def test_sharpe_que_vira_negativo_alerta(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, sharpe=1.5),
                    medidas(Particao.VALIDATION, sharpe=-0.4))

    assert "sharpe_virou_negativo" in chaves(rel)


def test_amostra_pequena_fora_da_amostra_e_observacao(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, trades=40),
                    medidas(Particao.VALIDATION, trades=4))

    alerta = next(a for a in rel.alertas if a.chave == "amostra_pequena")
    assert alerta.severidade is Severidade.OBSERVACAO
    assert alerta.particao is Particao.VALIDATION


def test_os_criterios_de_degradacao_sao_configuraveis(divisao):
    treino, validacao = medidas(Particao.TRAIN, retorno=10.0), medidas(
        Particao.VALIDATION, retorno=6.0)

    padrao = relatorio(divisao, treino, validacao)
    exigente = relatorio(divisao, treino, validacao,
                         criterios=CriteriosDeDegradacao(queda_de_retorno_pct=20.0))

    assert "retorno_caiu" not in chaves(padrao)
    assert "retorno_caiu" in chaves(exigente)


# --- validar o que ja perdia no treino nao faz sentido ------------------------------


def test_treino_negativo_e_critico_mesmo_com_o_resto_bonito(divisao):
    """Foi o bug que o primeiro relatorio real mostrou: dizia que 'se manteve'."""
    rel = relatorio(divisao, medidas(Particao.TRAIN, retorno=-0.4, expectancy=-133.0),
                    medidas(Particao.VALIDATION, retorno=0.2, expectancy=190.0))

    assert "treino_negativo" in chaves(rel)
    assert rel.degradou is True
    assert "nem no periodo em que foi ajustada" in rel.veredito


def test_treino_com_poucos_trades_vira_observacao(divisao):
    rel = relatorio(divisao, medidas(Particao.TRAIN, trades=3))

    assert "treino_sem_amostra" in chaves(rel)


def test_sem_treino_o_relatorio_nao_inventa_comparacao(divisao):
    rel = relatorio(divisao, validacao=medidas(Particao.VALIDATION))

    assert rel.alertas == []
    assert "sem medida de treino" in rel.veredito


# --- o cofre entra no relatorio ------------------------------------------------------


def test_cofre_aberto_duas_vezes_vira_alerta_critico(divisao):
    cofre = CofreDeTeste(divisao.teste)
    cofre.abrir("medicao final")
    cofre.abrir("nova espiada depois de mexer nos parametros")

    rel = relatorio(divisao, medidas(Particao.TRAIN), medidas(Particao.VALIDATION),
                    medidas(Particao.TEST), cofre=cofre)

    alerta = next(a for a in rel.alertas if a.chave == "teste_contaminado")
    assert alerta.severidade is Severidade.CRITICO
    assert "out-of-sample" in alerta.mensagem


def test_cofre_aberto_uma_vez_nao_alerta(divisao):
    cofre = CofreDeTeste(divisao.teste)
    cofre.abrir("medicao final")

    rel = relatorio(divisao, medidas(Particao.TRAIN), medidas(Particao.VALIDATION),
                    medidas(Particao.TEST), cofre=cofre)

    assert "teste_contaminado" not in chaves(rel)


def test_o_relatorio_serializa_para_json():
    import json

    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    rel = relatorio(d, medidas(Particao.TRAIN), medidas(Particao.VALIDATION))

    json.dumps(rel.para_dict())  # nao levanta
