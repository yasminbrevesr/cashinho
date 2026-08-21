"""Avaliacao de pedidos: aprovacao, contrato de retorno e ordens invalidas."""

from __future__ import annotations

import pytest

from cashinho.core.risk import Limitador, MotivoRejeicao, PedidoOperacao, RiskConfig
from cashinho.models import Direction

from .factories import compra, config, gerente, venda


def test_contrato_de_retorno_tem_os_cinco_campos():
    d = gerente().avaliar(compra(entrada=10.0, stop=9.5))

    assert d.allowed is True
    assert isinstance(d.reason, str) and d.reason
    assert d.position_size == 2_000  # risco 1000 / 0,50 por acao
    assert d.monetary_risk == pytest.approx(1_000.0)
    assert d.portfolio_exposure == pytest.approx(20_000.0)


def test_risco_monetario_e_o_risco_real_e_nao_o_alvo():
    """Com risco por acao de R$ 3,00, o alvo de R$ 1.000 vira 333 acoes = R$ 999."""
    d = gerente().avaliar(compra(entrada=30.0, stop=27.0))

    assert d.position_size == 333
    assert d.monetary_risk == pytest.approx(999.0)
    assert d.risco_alvo == pytest.approx(1_000.0)


def test_venda_e_dimensionada_igual_a_compra():
    d = gerente().avaliar(venda(entrada=10.0, stop=10.5))

    assert d.allowed is True
    assert d.direcao is Direction.SHORT
    assert d.risco_por_acao == pytest.approx(0.5)
    assert d.position_size == 2_000


def test_exposicao_reportada_soma_a_ordem_quando_aprovada():
    rm = gerente(config(exposicao_max_por_ativo_pct=50.0, exposicao_max_total_pct=100.0,
                        permitir_piramide=True))
    primeira = rm.avaliar(compra(entrada=10.0, stop=9.5))
    rm.abrir(primeira)

    segunda = rm.avaliar(compra(entrada=10.0, stop=9.5, symbol="VALE3"))
    assert segunda.portfolio_exposure == pytest.approx(
        rm.estado.exposicao_total() + segunda.exposicao_da_ordem
    )


def test_exposicao_reportada_e_a_atual_quando_rejeitada():
    rm = gerente()
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    rm.acionar_kill_switch("teste")

    d = rm.avaliar(compra(entrada=10.0, stop=9.5, symbol="VALE3"))
    assert d.allowed is False
    assert d.position_size == 0
    assert d.monetary_risk == 0.0
    assert d.portfolio_exposure == pytest.approx(rm.estado.exposicao_total())


def test_avaliar_nao_altera_o_estado():
    rm = gerente()
    antes = rm.estado.para_dict()

    rm.avaliar(compra())
    rm.avaliar(compra())

    assert rm.estado.para_dict() == antes
    assert rm.estado.trades_dia == 0


# --- ordens invalidas ---------------------------------------------------------


@pytest.mark.parametrize(
    "pedido,trecho",
    [
        (PedidoOperacao("PETR4", Direction.LONG, 10.0, 10.0), "mesmo preco"),
        (PedidoOperacao("PETR4", Direction.LONG, 10.0, 10.5), "lado errado"),
        (PedidoOperacao("PETR4", Direction.SHORT, 10.0, 9.5), "lado errado"),
        (PedidoOperacao("PETR4", Direction.LONG, 0.0, 9.5), "entrada invalida"),
        (PedidoOperacao("PETR4", Direction.LONG, -10.0, 9.5), "entrada invalida"),
        (PedidoOperacao("PETR4", Direction.LONG, 10.0, 0.0), "stop invalido"),
        (PedidoOperacao("PETR4", Direction.LONG, 10.0, -1.0), "stop invalido"),
        (PedidoOperacao("", Direction.LONG, 10.0, 9.5), "ativo nao informado"),
    ],
)
def test_ordem_invalida_e_rejeitada_com_explicacao(pedido, trecho):
    d = gerente().avaliar(pedido)

    assert d.allowed is False
    assert d.position_size == 0
    assert MotivoRejeicao.ORDEM_INVALIDA.value in d.codigos
    assert trecho in d.reason


def test_stop_igual_a_entrada_nao_explode_por_divisao_por_zero():
    d = gerente().avaliar(PedidoOperacao("PETR4", Direction.LONG, 25.0, 25.0))
    assert d.allowed is False  # nao levanta ZeroDivisionError


# --- limites de tamanho --------------------------------------------------------


def test_risco_que_nao_paga_uma_acao_e_rejeitado():
    rm = gerente(config(capital=1_000.0, risco_por_trade_pct=0.1))  # R$ 1,00 de risco
    d = rm.avaliar(compra(entrada=50.0, stop=45.0))  # R$ 5,00 por acao

    assert d.allowed is False
    assert MotivoRejeicao.RISCO_INSUFICIENTE.value in d.codigos


def test_sem_fracionario_menos_de_um_lote_e_rejeitado():
    rm = gerente(config(capital=10_000.0, permitir_fracionario=False))
    d = rm.avaliar(compra(entrada=50.0, stop=48.0))  # 50 acoes < 1 lote

    assert d.allowed is False
    assert MotivoRejeicao.RISCO_INSUFICIENTE.value in d.codigos
    assert "lote padrao" in d.reason


def test_sem_fracionario_a_quantidade_desce_para_o_lote():
    rm = gerente(config(permitir_fracionario=False))
    d = rm.avaliar(compra(entrada=10.0, stop=9.6))  # 2500 acoes

    assert d.position_size == 2_500
    d2 = gerente(config(capital=100_000.0, risco_por_trade_pct=0.255,
                        permitir_fracionario=False)).avaliar(compra(entrada=10.0, stop=9.0))
    assert d2.position_size == 200  # 255 acoes -> 2 lotes


def test_capital_insuficiente_e_rejeitado():
    """O risco pagaria 5 acoes, mas o caixa nao paga nem uma."""
    rm = gerente(config(capital=100.0, risco_por_trade_pct=50.0, perda_max_diaria_pct=100.0))
    d = rm.avaliar(compra(entrada=500.0, stop=490.0))

    assert d.allowed is False
    assert MotivoRejeicao.CAPITAL_INSUFICIENTE.value in d.codigos


def test_risco_por_trade_nunca_passa_do_que_resta_da_perda_diaria():
    """Arriscar 5% com perda diaria de 3% seria furar o limite no primeiro trade."""
    rm = gerente(config(capital=100_000.0, risco_por_trade_pct=5.0, perda_max_diaria_pct=3.0))
    d = rm.avaliar(compra(entrada=10.0, stop=9.0))

    assert d.risco_alvo == pytest.approx(3_000.0)  # e nao 5.000
    assert d.monetary_risk <= 3_000.0 + 1e-6
    assert d.limitador is Limitador.RISCO_DIARIO


def test_exposicao_por_ativo_limita_o_tamanho():
    rm = gerente(config(exposicao_max_por_ativo_pct=10.0))
    d = rm.avaliar(compra(entrada=10.0, stop=9.5))

    assert d.position_size == 1_000  # 10% de 100 mil / R$ 10
    assert d.limitador is Limitador.EXPOSICAO_ATIVO
    assert d.monetary_risk == pytest.approx(500.0)  # arrisca menos que o alvo


def test_exposicao_total_limita_o_tamanho():
    rm = gerente(config(exposicao_max_por_ativo_pct=30.0, exposicao_max_total_pct=30.0,
                        permitir_piramide=True))
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5, symbol="PETR4")))  # ocupa 20 mil

    d = rm.avaliar(compra(entrada=10.0, stop=9.5, symbol="VALE3"))
    assert d.limitador is Limitador.EXPOSICAO_TOTAL
    assert d.position_size == 1_000  # so os 10 mil que sobraram do teto
    assert rm.estado.exposicao_total() + d.exposicao_da_ordem <= 30_000.0 + 1e-6


def test_exposicao_esgotada_rejeita_a_ordem():
    rm = gerente(config(exposicao_max_por_ativo_pct=20.0, exposicao_max_total_pct=20.0,
                        permitir_piramide=True))
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))  # ocupa os 20 mil

    d = rm.avaliar(compra(entrada=10.0, stop=9.5, symbol="VALE3"))
    assert d.allowed is False
    assert MotivoRejeicao.EXPOSICAO_TOTAL.value in d.codigos


def test_posicao_existente_bloqueia_quando_piramide_esta_desligada():
    rm = gerente(config(permitir_piramide=False))
    rm.abrir(rm.avaliar(compra()))

    d = rm.avaliar(compra())
    assert d.allowed is False
    assert MotivoRejeicao.POSICAO_EXISTENTE.value in d.codigos


def test_piramide_ligada_permite_segunda_entrada_no_mesmo_ativo():
    rm = gerente(config(permitir_piramide=True, exposicao_max_por_ativo_pct=100.0))
    rm.abrir(rm.avaliar(compra()))

    with pytest.raises(ValueError):  # o estado ainda nao suporta somar posicoes
        rm.abrir(rm.avaliar(compra()))
