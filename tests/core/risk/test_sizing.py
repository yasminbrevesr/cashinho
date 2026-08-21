"""As contas do dimensionamento, isoladas de qualquer estado."""

from __future__ import annotations

import pytest

from cashinho.core.risk import (
    Limitador,
    ajusta_ao_lote,
    dimensionar,
    quantidade_por_financeiro,
    quantidade_por_risco,
    risco_monetario,
    risco_por_acao,
)


# --- formulas basicas -------------------------------------------------------


def test_risco_monetario_e_capital_vezes_percentual():
    assert risco_monetario(100_000, 1.0) == 1_000.0
    assert risco_monetario(50_000, 0.5) == 250.0


def test_risco_monetario_respeita_o_teto_absoluto():
    assert risco_monetario(100_000, 1.0, teto=300.0) == 300.0
    assert risco_monetario(10_000, 1.0, teto=300.0) == 100.0  # teto nao aumenta o risco


def test_risco_por_acao_e_a_distancia_ate_o_stop():
    assert risco_por_acao(31.00, 30.70) == pytest.approx(0.30)
    assert risco_por_acao(30.70, 31.00) == pytest.approx(0.30)  # simetrico (serve para venda)


def test_quantidade_e_o_piso_da_divisao():
    assert quantidade_por_risco(1_000, 3.0) == 333  # 333,33 -> 333, nunca 334
    assert quantidade_por_risco(1_000, 1.0) == 1_000
    assert quantidade_por_risco(99, 100.0) == 0


def test_piso_tolera_ruido_de_ponto_flutuante():
    """0,1+0,2 nao e' 0,3 em float: o piso nao pode devolver 999."""
    assert quantidade_por_risco(300.0, 0.1 + 0.2) == 1_000


def test_risco_por_acao_zero_nao_dimensiona():
    with pytest.raises(ZeroDivisionError):
        quantidade_por_risco(1_000, 0.0)


def test_risco_negativo_ou_zero_gera_quantidade_zero():
    assert quantidade_por_risco(0.0, 0.5) == 0
    assert quantidade_por_risco(-100.0, 0.5) == 0


def test_quantidade_por_financeiro():
    assert quantidade_por_financeiro(10_000, 31.0) == 322
    assert quantidade_por_financeiro(0, 31.0) == 0
    assert quantidade_por_financeiro(-500, 31.0) == 0
    with pytest.raises(ValueError):
        quantidade_por_financeiro(1_000, 0.0)


# --- lote --------------------------------------------------------------------


def test_lote_padrao_arredonda_para_baixo():
    assert ajusta_ao_lote(250, 100, permitir_fracionario=False) == 200
    assert ajusta_ao_lote(99, 100, permitir_fracionario=False) == 0
    assert ajusta_ao_lote(100, 100, permitir_fracionario=False) == 100


def test_fracionario_mantem_a_quantidade_exata():
    assert ajusta_ao_lote(250, 100, permitir_fracionario=True) == 250
    assert ajusta_ao_lote(7, 100, permitir_fracionario=True) == 7


# --- dimensionamento completo -------------------------------------------------


def _dim(**campos):
    base = dict(
        entrada=10.0,
        stop=9.5,
        risco_alvo=1_000.0,
        caixa_disponivel=1_000_000.0,
        teto_ativo_restante=1_000_000.0,
        teto_total_restante=1_000_000.0,
        permitir_fracionario=True,
    )
    base.update(campos)
    return dimensionar(**base)


def test_sem_restricao_quem_manda_e_o_risco():
    d = _dim()
    assert d.quantidade == 2_000  # 1000 / 0,50
    assert d.limitador is Limitador.RISCO
    assert d.risco_efetivo == pytest.approx(1_000.0)
    assert d.exposicao == pytest.approx(20_000.0)


def test_capital_corta_a_quantidade():
    d = _dim(caixa_disponivel=5_000.0)
    assert d.quantidade == 500
    assert d.limitador is Limitador.CAPITAL


def test_exposicao_por_ativo_corta_a_quantidade():
    d = _dim(teto_ativo_restante=8_000.0)
    assert d.quantidade == 800
    assert d.limitador is Limitador.EXPOSICAO_ATIVO


def test_exposicao_total_corta_a_quantidade():
    d = _dim(teto_total_restante=3_000.0)
    assert d.quantidade == 300
    assert d.limitador is Limitador.EXPOSICAO_TOTAL


def test_vence_sempre_a_restricao_mais_apertada():
    d = _dim(caixa_disponivel=9_000.0, teto_ativo_restante=7_000.0, teto_total_restante=8_000.0)
    assert d.quantidade == 700
    assert d.limitador is Limitador.EXPOSICAO_ATIVO


def test_no_empate_o_risco_explica_melhor():
    """Risco e exposicao dao a mesma quantidade: o motivo reportado e' o risco."""
    d = _dim(teto_ativo_restante=20_000.0)  # tambem da 2000 acoes
    assert d.quantidade == 2_000
    assert d.limitador is Limitador.RISCO


def test_lote_aplicado_depois_dos_cortes():
    d = _dim(caixa_disponivel=2_550.0, permitir_fracionario=False)
    assert d.quantidade == 200  # 255 acoes viram 2 lotes
    assert d.limitador is Limitador.CAPITAL


def test_dimensionamento_zerado_e_sinalizado():
    d = _dim(caixa_disponivel=5.0)
    assert d.quantidade == 0
    assert d.zerado is True
    assert d.risco_efetivo == 0.0


def test_entrada_invalida_e_recusada():
    with pytest.raises(ValueError):
        _dim(entrada=0.0)
