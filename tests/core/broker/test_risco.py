"""A trava: nenhuma ordem de entrada chega a corretora sem o Risk Manager."""

from __future__ import annotations

import pytest

from cashinho.core.broker import BrokerComRisco, Order, OrderStatus, OrderType, PaperBroker
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.models import Direction

from .factories import candle, com_risco, ordem, paper, risco_folgado


class BrokerEspiao(PaperBroker):
    """Registra tudo o que chega - para provar o que NAO chegou."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recebidas: list[Order] = []

    def place_order(self, order: Order) -> Order:
        self.recebidas.append(order)
        return super().place_order(order)


def _espiao(**campos):
    from cashinho.core.backtest.costs import SEM_CUSTOS
    from cashinho.core.broker.paper import ConfigPaper

    from .factories import relogio

    b = BrokerEspiao(ConfigPaper(capital_inicial=100_000.0, custos=SEM_CUSTOS, **campos),
                     relogio())
    b.atualizar_preco("PETR4", 31.00)
    return b


# --- a trava --------------------------------------------------------------------


def test_ordem_de_entrada_sem_stop_nao_chega_na_corretora():
    espiao = _espiao()
    b = BrokerComRisco(espiao, risco_folgado())

    o = b.place_order(ordem(OrderType.MARKET, quantidade=100))

    assert o.status is OrderStatus.REJEITADA
    assert "sem stop de referencia" in o.motivo
    assert espiao.recebidas == []


def test_ordem_rejeitada_pelo_risco_nao_chega_na_corretora():
    espiao = _espiao()
    risco = risco_folgado()
    risco.acionar_kill_switch("mercado maluco")
    b = BrokerComRisco(espiao, risco)

    o = b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))

    assert o.status is OrderStatus.REJEITADA
    assert "kill switch" in o.motivo
    assert espiao.recebidas == []


def test_a_quantidade_e_a_que_o_risco_autorizou():
    """1% de 100 mil com stop a R$ 0,30 = 3.333 acoes, nao as 100 mil pedidas."""
    b = com_risco(risco=risco_folgado(risco_por_trade_pct=1.0))
    o = b.place_order(ordem(OrderType.MARKET, quantidade=100_000, stop_referencia=30.70))

    assert o.status is OrderStatus.EXECUTADA
    assert o.quantidade == 3_225  # limitado tambem pelo caixa
    assert o.quantidade < 100_000


def test_pedido_menor_que_o_autorizado_e_respeitado():
    b = com_risco()
    o = b.place_order(ordem(OrderType.MARKET, quantidade=50, stop_referencia=30.70))

    assert o.quantidade == 50


def test_risco_que_autoriza_zero_barra_a_ordem():
    magro = risco_folgado(capital=100.0, exposicao_max_por_ativo_pct=1.0)
    b = com_risco(paper(capital=100.0), magro)

    o = b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))

    assert o.status is OrderStatus.REJEITADA


# --- saida sempre permitida ----------------------------------------------------------


def test_ordem_que_reduz_posicao_passa_sem_dimensionamento():
    """Uma trava que impede de sair da posicao seria pior do que trava nenhuma."""
    espiao = _espiao()
    b = BrokerComRisco(espiao, risco_folgado())
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    b.risco.acionar_kill_switch("trava geral")

    saida = b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))

    assert saida.status is OrderStatus.EXECUTADA
    assert espiao.recebidas[-1] is saida


def test_stop_loss_passa_mesmo_com_o_risco_travado():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    b.risco.acionar_kill_switch("trava")

    sl = b.place_order(ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100,
                             preco_disparo=30.50))

    assert sl.status is OrderStatus.PENDENTE


# --- espelho no Risk Manager ------------------------------------------------------------


def test_execucao_abre_posicao_no_risk_manager():
    risco = risco_folgado()
    b = com_risco(risco=risco)
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))

    assert "PETR4" in risco.estado.posicoes
    assert risco.estado.posicoes["PETR4"].quantidade == 100
    assert risco.estado.trades_dia == 1


def test_encerramento_fecha_a_posicao_no_risk_manager():
    risco = risco_folgado()
    b = com_risco(risco=risco)
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    b.broker.atualizar_preco("PETR4", 32.00)
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=100))

    assert "PETR4" not in risco.estado.posicoes
    assert risco.estado.pnl_dia > 0


def test_ordem_pendente_so_entra_no_risco_quando_executa():
    risco = risco_folgado()
    b = com_risco(risco=risco)
    b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.50,
                        stop_referencia=30.00))

    assert risco.estado.posicoes == {}

    b.processar("PETR4", candle(30.9, 31.0, 30.40, 30.60))
    assert "PETR4" in risco.estado.posicoes


def test_limites_do_risco_valem_ao_longo_da_sessao():
    risco = risco_folgado(max_trades_dia=1)
    b = com_risco(risco=risco)

    primeira = b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    b.broker.atualizar_preco("VALE3", 60.0)
    segunda = b.place_order(ordem(OrderType.MARKET, quantidade=100, symbol="VALE3",
                                  stop_referencia=59.0))

    assert primeira.status is OrderStatus.EXECUTADA
    assert segunda.status is OrderStatus.REJEITADA
    assert "maximo" in segunda.motivo or "trades" in segunda.motivo


# --- kill switch dos dois lados ---------------------------------------------------------------


def test_kill_switch_trava_risco_e_corretora():
    b = com_risco()
    b.place_order(ordem(OrderType.LIMIT, quantidade=100, preco_limite=30.0,
                        stop_referencia=29.5))

    canceladas = b.acionar_kill_switch("fim do expediente")

    assert b.risco.estado.kill_switch is not None
    assert b.broker.kill_switch_ativo is True
    assert len(canceladas) == 1
    assert b.get_orders(abertas=True) == []


def test_kill_switch_nao_cancela_protecao_de_posicao():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    sl = b.place_order(ordem(OrderType.STOP_LOSS, side=Direction.SHORT, quantidade=100,
                             preco_disparo=30.50))

    b.acionar_kill_switch("trava")

    assert sl.status is OrderStatus.PENDENTE


def test_kill_switch_pode_ser_liberado():
    b = com_risco()
    b.acionar_kill_switch("teste")
    b.liberar_kill_switch()

    o = b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    assert o.status is OrderStatus.EXECUTADA


# --- interface preservada -------------------------------------------------------------------------


def test_o_wrapper_implementa_a_mesma_interface():
    from cashinho.core.broker import Broker

    b = com_risco()
    assert isinstance(b, Broker)
    for metodo in ("place_order", "cancel_order", "get_orders", "get_positions", "get_balance"):
        assert callable(getattr(b, metodo))


def test_ordens_barradas_aparecem_no_historico():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))  # sem stop

    todas = b.get_orders()
    assert any(o.status is OrderStatus.REJEITADA for o in todas)
    assert b.get_orders(abertas=True) == []
