"""Spread, slippage e taxas - sempre contra o trade."""

from __future__ import annotations

import pytest

from cashinho.core.backtest import SEM_CUSTOS, ModeloCustos
from cashinho.models import Direction

CUSTOS = ModeloCustos(spread_ticks=2.0, slippage_ticks=1.0, tick=0.01,
                      corretagem_fixa=5.0, corretagem_pct=0.0, taxas_b3_pct=0.03)


def test_compra_executa_acima_do_preco_visto():
    # meio spread (1 tick) + slippage (1 tick) = 2 centavos acima
    assert CUSTOS.preco_execucao(30.00, Direction.LONG, entrando=True) == pytest.approx(30.02)


def test_venda_de_encerramento_executa_abaixo():
    assert CUSTOS.preco_execucao(30.00, Direction.LONG, entrando=False) == pytest.approx(29.98)


def test_venda_a_descoberto_tambem_paga_o_spread():
    """Abrir vendido executa no bid; recomprar executa no ask."""
    abertura = CUSTOS.preco_execucao(30.00, Direction.SHORT, entrando=True)
    fechamento = CUSTOS.preco_execucao(30.00, Direction.SHORT, entrando=False)

    assert abertura == pytest.approx(29.98)
    assert fechamento == pytest.approx(30.02)


def test_ordem_limitada_no_alvo_nao_derrapa():
    limitada = CUSTOS.preco_execucao(31.00, Direction.LONG, entrando=False, ordem_limitada=True)
    mercado = CUSTOS.preco_execucao(31.00, Direction.LONG, entrando=False)

    assert limitada == pytest.approx(30.99)  # so o meio spread
    assert mercado < limitada  # o stop, virando mercado, sai pior


def test_slippage_no_alvo_pode_ser_ligado():
    pessimista = ModeloCustos(spread_ticks=2.0, slippage_ticks=1.0, slippage_no_alvo=True)
    assert pessimista.preco_execucao(31.00, Direction.LONG, entrando=False,
                                     ordem_limitada=True) == pytest.approx(30.98)


def test_arredondamento_nunca_favorece_o_trade():
    """Meio tick de spread: comprando sobe para o tick, vendendo desce."""
    meio = ModeloCustos(spread_ticks=1.0, slippage_ticks=0.0, tick=0.01)

    assert meio.preco_execucao(30.00, Direction.LONG, entrando=True) == pytest.approx(30.01)
    assert meio.preco_execucao(30.00, Direction.LONG, entrando=False) == pytest.approx(29.99)


def test_taxas_cobram_as_duas_pontas():
    uma_ponta = CUSTOS.taxas(1_000, 30.0)
    total = CUSTOS.custo_total(1_000, 30.0, 30.0)

    assert uma_ponta == pytest.approx(5.0 + 30_000 * 0.0003)
    assert total == pytest.approx(2 * uma_ponta)


def test_corretagem_percentual_entra_na_conta():
    c = ModeloCustos(corretagem_fixa=0.0, corretagem_pct=0.1, taxas_b3_pct=0.0)
    assert c.taxas(100, 50.0) == pytest.approx(5_000 * 0.001)


def test_modelo_sem_custos_nao_mexe_no_preco():
    assert SEM_CUSTOS.preco_execucao(30.00, Direction.LONG, entrando=True) == pytest.approx(30.00)
    assert SEM_CUSTOS.custo_total(1_000, 30.0, 31.0) == 0.0


def test_valores_negativos_sao_recusados():
    with pytest.raises(ValueError):
        ModeloCustos(spread_ticks=-1)
    with pytest.raises(ValueError):
        ModeloCustos(tick=0)
