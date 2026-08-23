"""O fluxo completo: treino, validacao e - so no fim - o teste."""

from __future__ import annotations

import pytest

from cashinho.core.backtest.config import BacktestConfig
from cashinho.core.oportunidade import EstrategiaOportunidade
from cashinho.core.validacao import (
    Candidato,
    DivisaoDeDados,
    Particao,
    ValidadorDeEstrategia,
)

from .factories import config_validacao, serie_de_dias


def validador(**campos):
    return ValidadorDeEstrategia(EstrategiaOportunidade, config_validacao(**campos))


@pytest.fixture
def divisao():
    return DivisaoDeDados.por_percentual(serie_de_dias(dias=12))


def test_o_relatorio_traz_as_tres_particoes(divisao):
    rel = validador().validar(divisao)

    assert {m.particao for m in rel.medidas.values()} == {
        Particao.TRAIN, Particao.VALIDATION, Particao.TEST}


def test_o_cofre_e_aberto_exatamente_uma_vez(divisao):
    rel = validador().validar(divisao)

    assert rel.cofre.vezes == 1
    assert rel.cofre.contaminado is False


def test_o_motivo_da_abertura_fica_registrado(divisao):
    rel = validador().validar(divisao)

    assert "medicao final" in rel.cofre.aberturas[0].motivo


def test_da_para_validar_sem_abrir_o_cofre(divisao):
    rel = validador().validar(divisao, medir_teste=False)

    assert rel.cofre.foi_aberto is False
    assert rel.medida(Particao.TEST) is None
    assert rel.medida(Particao.TRAIN) is not None


def test_o_test_e_medido_depois_da_escolha_e_nao_antes(divisao):
    """Ordem observavel: tudo que toca no TEST vem depois da selecao."""
    from cashinho.core.validacao import CriteriosDeSelecao

    ordem = []
    # criterios frouxos so para garantir que a selecao aprove alguem e o fluxo
    # chegue ate o fim; o que o teste observa e' a ORDEM, nao a escolha
    v = validador(criterios_selecao=CriteriosDeSelecao(
        min_trades_treino=0, min_trades_validacao=0, profit_factor_minimo=0.0,
        exigir_retorno_positivo=False))
    medir_original = v.medir

    def espiao(janela, serie, cfg=None):
        ordem.append(janela.particao)
        return medir_original(janela, serie, cfg)

    v.medir = espiao
    rel = v.validar(divisao, [Candidato("a", None), Candidato("b", None)])

    assert rel.selecao.houve_escolha is True
    assert ordem[-1] is Particao.TEST
    assert Particao.TEST not in ordem[:-1]


def test_a_janela_medida_e_a_da_particao(divisao):
    v = validador()
    resultado = v.medir(divisao.validacao, divisao.serie)

    if resultado.trades:
        for t in resultado.trades:
            assert divisao.validacao.inicio <= t.entrada.ts.date() <= divisao.validacao.fim


def test_o_aquecimento_nao_gera_trades_fora_da_janela(divisao):
    """O aquecimento alimenta indicadores; ele nao pode virar operacao."""
    v = validador(dias_de_aquecimento=3)
    resultado = v.medir(divisao.teste, divisao.serie)

    for t in resultado.trades:
        assert t.entrada.ts.date() >= divisao.teste.inicio


def test_selecao_sem_candidato_aprovado_nao_abre_o_cofre(divisao):
    """Se nada passou na validacao, nao ha o que medir no TEST."""
    from cashinho.core.validacao import CriteriosDeSelecao

    v = validador(criterios_selecao=CriteriosDeSelecao(min_trades_treino=10_000))
    rel = v.validar(divisao, [Candidato("a", None)])

    assert rel.selecao.houve_escolha is False
    assert rel.cofre.foi_aberto is False
    assert rel.medidas == {}


def test_o_relatorio_diz_qual_candidato_foi_medido(divisao):
    rel = validador().validar(divisao)

    assert rel.candidato == "configuracao unica"
