"""O PaperBroker: tipos de ordem, custos, saldo e posicao existente."""

from __future__ import annotations

import pytest

from cashinho.core.backtest.costs import ModeloCustos
from cashinho.core.broker import (
    BrokerError,
    ConfigPaper,
    Order,
    OrderStatus,
    OrderType,
    PaperBroker,
)
from cashinho.models import Direction

from .factories import AGORA, candle, ordem, paper


# --- interface ------------------------------------------------------------------


def test_implementa_os_cinco_metodos_do_contrato():
    b = paper()

    assert callable(b.place_order) and callable(b.cancel_order)
    assert callable(b.get_orders) and callable(b.get_positions) and callable(b.get_balance)


def test_conta_nova_comeca_com_o_capital_em_caixa():
    b = paper(capital=50_000.0)
    saldo = b.get_balance()

    assert saldo.saldo == 50_000.0
    assert saldo.patrimonio == 50_000.0
    assert saldo.posicoes_abertas == 0


# --- market -----------------------------------------------------------------------


def test_ordem_a_mercado_executa_na_hora():
    b = paper()
    o = b.place_order(ordem(OrderType.MARKET, quantidade=100))

    assert o.status is OrderStatus.EXECUTADA
    assert o.preco_executado == pytest.approx(31.00)
    assert b.get_positions()[0].quantidade == 100


def test_mercado_sem_preco_conhecido_e_rejeitada():
    b = paper(preco=None)
    o = b.place_order(ordem(OrderType.MARKET))

    assert o.status is OrderStatus.REJEITADA
    assert "sem preco conhecido" in o.motivo


# --- limit --------------------------------------------------------------------------


def test_ordem_limitada_fica_pendente_ate_o_preco_chegar():
    b = paper()
    o = b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.50))

    assert o.status is OrderStatus.PENDENTE
    b.processar("PETR4", candle(31.0, 31.2, 30.8, 30.9))  # nao chegou
    assert o.status is OrderStatus.PENDENTE

    b.processar("PETR4", candle(30.9, 31.0, 30.40, 30.60))  # tocou
    assert o.status is OrderStatus.EXECUTADA
    assert o.preco_executado == pytest.approx(30.50)


def test_limitada_de_compra_com_gap_executa_melhor():
    b = paper()
    o = b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.50))
    b.processar("PETR4", candle(30.10, 30.30, 30.00, 30.20))  # abriu abaixo do limite

    assert o.preco_executado == pytest.approx(30.10)  # a abertura, a favor


def test_limitada_exige_preco():
    o = paper().place_order(ordem(OrderType.LIMIT, quantidade=100))

    assert o.status is OrderStatus.REJEITADA
    assert "exige preco limite" in o.motivo


# --- stop de entrada --------------------------------------------------------------------


def test_stop_de_compra_dispara_para_cima():
    b = paper()
    o = b.place_order(ordem(OrderType.STOP, quantidade=100, preco_disparo=31.50))

    b.processar("PETR4", candle(31.0, 31.30, 30.9, 31.20))
    assert o.status is OrderStatus.PENDENTE

    b.processar("PETR4", candle(31.2, 31.80, 31.1, 31.70))
    assert o.status is OrderStatus.EXECUTADA
    assert o.preco_executado == pytest.approx(31.50)


def test_stop_com_gap_executa_na_abertura_pior():
    b = paper()
    o = b.place_order(ordem(OrderType.STOP, quantidade=100, preco_disparo=31.50))
    b.processar("PETR4", candle(32.00, 32.20, 31.90, 32.10))

    assert o.preco_executado == pytest.approx(32.00)


# --- stop loss e take profit ---------------------------------------------------------------


def test_stop_loss_exige_posicao_aberta():
    o = paper().place_order(
        ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100, preco_disparo=30.5)
    )

    assert o.status is OrderStatus.REJEITADA
    assert "sem posicao aberta" in o.motivo


def test_stop_loss_encerra_a_posicao():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    sl = b.place_order(ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100,
                             preco_disparo=30.50))

    b.processar("PETR4", candle(31.0, 31.1, 30.20, 30.40))

    assert sl.status is OrderStatus.EXECUTADA
    assert b.get_positions() == []
    assert b.get_trades()[0].resultado < 0


def test_take_profit_encerra_no_lucro():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    tp = b.place_order(ordem(OrderType.TAKE_PROFIT, side=Direction.SHORT, quantidade=100,
                             preco_limite=31.60))

    b.processar("PETR4", candle(31.0, 31.80, 30.95, 31.70))

    assert tp.status is OrderStatus.EXECUTADA
    assert b.get_trades()[0].resultado > 0


# --- OCO ---------------------------------------------------------------------------------


def test_oco_cancela_a_outra_perna_quando_uma_executa():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    sl, tp = b.place_oco(
        ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100, preco_disparo=30.50),
        ordem(OrderType.TAKE_PROFIT, side=Direction.SHORT, quantidade=100, preco_limite=31.60),
    )
    assert sl.oco_id == tp.oco_id

    b.processar("PETR4", candle(31.0, 31.80, 30.95, 31.70))

    assert tp.status is OrderStatus.EXECUTADA
    assert sl.status is OrderStatus.CANCELADA
    assert "OCO" in sl.motivo


def test_quando_stop_e_alvo_cabem_no_mesmo_candle_o_stop_vem_primeiro():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    sl, tp = b.place_oco(
        ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100, preco_disparo=30.50),
        ordem(OrderType.TAKE_PROFIT, side=Direction.SHORT, quantidade=100, preco_limite=31.60),
    )
    b.processar("PETR4", candle(31.0, 31.80, 30.20, 31.00))  # bateu os dois

    assert sl.status is OrderStatus.EXECUTADA
    assert tp.status is OrderStatus.CANCELADA


def test_a_prioridade_intracandle_e_configuravel():
    b = paper(custos=None, prioridade_intracandle="alvo")
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    sl, tp = b.place_oco(
        ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100, preco_disparo=30.50),
        ordem(OrderType.TAKE_PROFIT, side=Direction.SHORT, quantidade=100, preco_limite=31.60),
    )
    b.processar("PETR4", candle(31.0, 31.80, 30.20, 31.00))

    assert tp.status is OrderStatus.EXECUTADA
    assert sl.status is OrderStatus.CANCELADA


# --- custos, spread e slippage --------------------------------------------------------------


def test_spread_e_slippage_pioram_o_preco():
    com_atrito = paper(custos=ModeloCustos(spread_ticks=2.0, slippage_ticks=1.0, taxas_b3_pct=0.0))
    compra = com_atrito.place_order(ordem(OrderType.MARKET, quantidade=100))

    assert compra.preco_executado == pytest.approx(31.02)


def test_taxas_saem_do_caixa():
    b = paper(custos=ModeloCustos(corretagem_fixa=5.0, taxas_b3_pct=0.03,
                                  spread_ticks=0.0, slippage_ticks=0.0))
    o = b.place_order(ordem(OrderType.MARKET, quantidade=100))

    esperado = 100 * 31.0 * 0.0003 + 5.0
    assert o.custos == pytest.approx(esperado)
    assert b.get_balance().saldo == pytest.approx(100_000.0 - 3_100.0 - esperado)


def test_custos_entram_no_resultado_da_operacao():
    b = paper(custos=ModeloCustos(corretagem_fixa=5.0, spread_ticks=0.0, slippage_ticks=0.0,
                                  taxas_b3_pct=0.0))
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))
    operacao = b.get_trades()[0]

    assert operacao.custos > 0
    assert operacao.resultado == pytest.approx(operacao.resultado_bruto - operacao.custos)


# --- saldo -------------------------------------------------------------------------------------


def test_compra_maior_que_o_caixa_e_rejeitada():
    b = paper(capital=1_000.0)
    o = b.place_order(ordem(OrderType.MARKET, quantidade=1_000))

    assert o.status is OrderStatus.REJEITADA
    assert "saldo insuficiente" in o.motivo
    assert b.get_positions() == []


def test_venda_credita_o_caixa():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    saldo_apos_compra = b.get_balance().saldo
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))

    assert b.get_balance().saldo > saldo_apos_compra


def test_patrimonio_soma_caixa_e_posicoes():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    saldo = b.get_balance()

    assert saldo.patrimonio == pytest.approx(saldo.saldo + 100 * 31.0)


# --- posicao existente ---------------------------------------------------------------------------


def test_compra_em_cima_de_compra_faz_preco_medio():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.atualizar_preco("PETR4", 33.00)
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    posicao = b.get_positions()[0]

    assert posicao.quantidade == 200
    assert posicao.preco_medio == pytest.approx(32.00)


def test_venda_parcial_reduz_a_posicao_e_registra_operacao():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=200))
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=50))

    assert b.get_positions()[0].quantidade == 150
    assert len(b.get_trades()) == 1
    assert b.get_trades()[0].quantidade == 50


def test_venda_maior_que_a_posicao_inverte_o_lado():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=300))
    posicao = b.get_positions()[0]

    assert posicao.quantidade == -200
    assert posicao.direcao is Direction.SHORT
    assert len(b.get_trades()) == 1  # a parte que fechou


def test_venda_a_descoberto_pode_ser_desligada():
    b = paper(permitir_venda_descoberto=False)
    o = b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))

    assert o.status is OrderStatus.REJEITADA
    assert "descoberto" in o.motivo


# --- cancelamento e consultas ------------------------------------------------------------------------


def test_cancelar_ordem_pendente():
    b = paper()
    o = b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.0))
    cancelada = b.cancel_order(o.id)

    assert cancelada.status is OrderStatus.CANCELADA
    assert b.get_orders(abertas=True) == []


def test_cancelar_ordem_desconhecida_levanta():
    with pytest.raises(BrokerError):
        paper().cancel_order("nao-existe")


def test_cancelar_todas():
    b = paper()
    b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.0))
    b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=29.0))

    assert len(b.cancel_all()) == 2
    assert b.get_orders(abertas=True) == []


def test_get_orders_filtra_por_ativo_e_por_abertas():
    b = paper()
    b.atualizar_preco("VALE3", 60.0)
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.place_order(ordem(OrderType.LIMIT, quantidade=100, symbol="VALE3", preco_limite=59.0))

    assert len(b.get_orders()) == 2
    assert len(b.get_orders("VALE3")) == 1
    assert len(b.get_orders(abertas=True)) == 1


def test_quantidade_zero_e_rejeitada():
    o = paper().place_order(ordem(OrderType.MARKET, quantidade=0))

    assert o.status is OrderStatus.REJEITADA
    assert "quantidade invalida" in o.motivo


# --- P&L ----------------------------------------------------------------------------------------------


def test_pnl_diario_e_acumulado():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.atualizar_preco("PETR4", 32.00)
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))
    saldo = b.get_balance()

    assert saldo.pnl_acumulado == pytest.approx(100.0)
    assert saldo.pnl_dia == pytest.approx(100.0)


def test_pnl_aberto_marca_a_posicao_a_mercado():
    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.atualizar_preco("PETR4", 31.50)

    assert b.pnl_aberto() == pytest.approx(50.0)
    assert b.get_balance().pnl_acumulado == 0.0  # so realizado


# --- persistencia -------------------------------------------------------------------------------------


def test_estado_vai_e_volta_do_disco():
    import json

    b = paper()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    b.place_order(ordem(OrderType.LIMIT, quantidade=50, preco_limite=30.0))
    b.acionar_kill_switch("teste")

    voltou = PaperBroker.de_dict(json.loads(json.dumps(b.para_dict())))

    assert voltou.get_balance().saldo == pytest.approx(b.get_balance().saldo)
    assert voltou.get_positions()[0].quantidade == 100
    assert voltou.kill_switch_ativo is True
    assert len(voltou.get_orders()) == len(b.get_orders())
