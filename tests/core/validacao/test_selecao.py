"""A selecao de parametros: pequena, e sem tocar no TEST."""

from __future__ import annotations

import pytest

from cashinho.core.backtest.config import BacktestConfig
from cashinho.core.oportunidade import EstrategiaOportunidade
from cashinho.core.validacao import (
    LIMITE_DE_CANDIDATOS,
    Candidato,
    CriteriosDeSelecao,
    DivisaoDeDados,
    GradeGrandeDemaisError,
    Particao,
    SelecionadorEmTreino,
    TesteProtegidoError,
    ValidadorDeEstrategia,
)
from cashinho.core.validacao.selecao import Medida

from .factories import config_validacao, serie_de_dias


class ResultadoFalso:
    """Resultado de backtest com as metricas que o teste quiser."""

    def __init__(self, retorno=1.0, trades=20, pf=1.5, expectancy=10.0):
        from cashinho.core.backtest.models import Metricas

        self.metricas = Metricas(
            retorno_total_pct=retorno, n_trades=trades, profit_factor=pf,
            expectancy=expectancy, max_drawdown_pct=1.0, sharpe=1.0,
        )


def _selecionador(resultados: dict, criterios=None):
    """Devolve um resultado combinado por (particao, candidato)."""
    def avaliar(janela, config):
        return resultados[(janela.particao, config)]

    return SelecionadorEmTreino(avaliar, criterios)


# --- limite de grade ------------------------------------------------------------


def test_a_grade_grande_e_recusada():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato(f"c{i}", f"cfg{i}") for i in range(LIMITE_DE_CANDIDATOS + 1)]

    with pytest.raises(GradeGrandeDemaisError, match="encontra ruido"):
        _selecionador({}).selecionar(d, candidatos)


def test_o_limite_e_pequeno_de_proposito():
    assert LIMITE_DE_CANDIDATOS <= 20


def test_sem_candidatos_e_erro():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    with pytest.raises(ValueError):
        _selecionador({}).selecionar(d, [])


# --- o fluxo treino -> validacao --------------------------------------------------


def test_escolhe_pelo_desempenho_na_validacao_e_nao_no_treino():
    """O melhor no treino costuma ser o mais ajustado ao passado."""
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("ajustado", "A"), Candidato("solido", "B")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=20.0, trades=30),
        (Particao.TRAIN, "B"): ResultadoFalso(retorno=5.0, trades=30),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=0.5, trades=10),
        (Particao.VALIDATION, "B"): ResultadoFalso(retorno=4.0, trades=10),
    }

    selecao = _selecionador(resultados).selecionar(d, candidatos)

    assert selecao.escolhido.nome == "solido"
    assert "validacao" in selecao.motivo


def test_candidato_sem_trades_suficientes_e_descartado():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("raro", "A"), Candidato("normal", "B")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=30.0, trades=3),
        (Particao.TRAIN, "B"): ResultadoFalso(retorno=5.0, trades=30),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=10.0, trades=2),
        (Particao.VALIDATION, "B"): ResultadoFalso(retorno=3.0, trades=10),
    }

    selecao = _selecionador(resultados).selecionar(d, candidatos)

    assert selecao.escolhido.nome == "normal"
    assert any(nome == "raro" for nome, _ in selecao.descartados)


def test_candidato_negativo_na_validacao_e_descartado():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("A", "A")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=30.0, trades=30),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=-2.0, trades=10),
    }

    selecao = _selecionador(resultados).selecionar(d, candidatos)

    assert selecao.houve_escolha is False
    assert "nenhum candidato" in selecao.motivo


def test_profit_factor_abaixo_de_um_na_validacao_descarta():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("A", "A")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=10.0, trades=30, pf=2.0),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=1.0, trades=10, pf=0.8),
    }

    assert _selecionador(resultados).selecionar(d, candidatos).houve_escolha is False


def test_os_criterios_sao_configuraveis():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("A", "A")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=10.0, trades=3),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=1.0, trades=2),
    }

    rigoroso = _selecionador(resultados).selecionar(d, candidatos)
    frouxo = _selecionador(
        resultados, CriteriosDeSelecao(min_trades_treino=1, min_trades_validacao=1)
    ).selecionar(d, candidatos)

    assert rigoroso.houve_escolha is False
    assert frouxo.houve_escolha is True


def test_a_selecao_registra_as_medidas_das_duas_particoes():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    candidatos = [Candidato("A", "A")]
    resultados = {
        (Particao.TRAIN, "A"): ResultadoFalso(retorno=10.0, trades=30),
        (Particao.VALIDATION, "A"): ResultadoFalso(retorno=3.0, trades=10),
    }

    selecao = _selecionador(resultados).selecionar(d, candidatos)
    dados = selecao.para_dict()

    assert len(dados["em_treino"]) == 1
    assert len(dados["em_validacao"]) == 1
    assert selecao.medida("A", Particao.TRAIN).retorno_pct == 10.0


# --- o TEST nao entra aqui ----------------------------------------------------------


def test_a_selecao_nunca_avalia_a_particao_test():
    """O avaliador so pode ser chamado com TRAIN e VALIDATION."""
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    vistas = []

    def avaliar(janela, config):
        vistas.append(janela.particao)
        return ResultadoFalso(retorno=5.0, trades=30)

    SelecionadorEmTreino(avaliar).selecionar(d, [Candidato("A", "A")])

    assert Particao.TEST not in vistas
    assert set(vistas) == {Particao.TRAIN, Particao.VALIDATION}


def test_passar_test_para_a_barreira_levanta():
    from cashinho.core.validacao import garantir_sem_teste

    with pytest.raises(TesteProtegidoError):
        garantir_sem_teste([Particao.TEST])
