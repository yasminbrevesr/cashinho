"""Perda diaria, numero de trades, perdas seguidas, drawdown e kill switch."""

from __future__ import annotations

from datetime import date

import pytest

from cashinho.core.risk import MotivoRejeicao
from cashinho.core.risk.models import Position, TradeResult
from cashinho.models import Direction

from .factories import AGORA, compra, config, ganhar, gerente, perder


# --- perda maxima diaria -------------------------------------------------------


def test_perda_diaria_no_limite_bloqueia():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0))
    perder(rm, 300.0)  # exatamente o limite

    d = rm.avaliar(compra())
    assert d.allowed is False
    assert MotivoRejeicao.KILL_SWITCH.value in d.codigos or MotivoRejeicao.PERDA_DIARIA.value in d.codigos


def test_perda_abaixo_do_limite_ainda_libera_mas_com_risco_menor():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0, risco_por_trade_pct=2.0))
    perder(rm, 250.0)  # sobram R$ 50 de risco no dia

    d = rm.avaliar(compra(entrada=10.0, stop=9.9))
    assert d.allowed is True
    assert d.risco_alvo == pytest.approx(50.0)
    assert d.monetary_risk <= 50.0 + 1e-6


def test_perda_diaria_usa_o_capital_da_abertura_e_nao_o_que_sobrou():
    """Se o limite acompanhasse o patrimonio encolhendo, ele nunca seria atingido."""
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0))
    perder(rm, 200.0)

    limite = rm.config.perda_max_diaria(rm.estado.capital_pregao)
    assert limite == pytest.approx(300.0)  # 3% dos 10 mil da abertura, nao dos 9.800


def test_ganho_no_dia_nao_aumenta_o_limite_de_perda():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0, risco_por_trade_pct=10.0))
    ganhar(rm, 500.0)

    d = rm.avaliar(compra(entrada=10.0, stop=9.0))
    assert d.risco_alvo == pytest.approx(300.0)  # continua 3% da abertura


# --- numero de trades -----------------------------------------------------------


def test_maximo_de_trades_no_dia():
    rm = gerente(config(max_trades_dia=2, permitir_piramide=False))
    for symbol in ("PETR4", "VALE3"):
        rm.abrir(rm.avaliar(compra(symbol=symbol)))

    d = rm.avaliar(compra(symbol="ITUB4"))
    assert d.allowed is False
    assert MotivoRejeicao.MAX_TRADES.value in d.codigos


def test_contador_de_trades_zera_no_novo_pregao():
    rm = gerente(config(max_trades_dia=1))
    rm.abrir(rm.avaliar(compra()))
    assert rm.avaliar(compra(symbol="VALE3")).allowed is False

    rm.fechar("PETR4", 10.5)
    rm.novo_pregao(date(2026, 8, 21))
    assert rm.avaliar(compra(symbol="VALE3")).allowed is True


# --- perdas consecutivas ---------------------------------------------------------


def test_perdas_consecutivas_bloqueiam():
    rm = gerente(config(max_perdas_consecutivas=3, max_trades_dia=10))
    for _ in range(3):
        perder(rm, 10.0)

    d = rm.avaliar(compra())
    assert d.allowed is False
    assert rm.estado.perdas_consecutivas == 3


def test_um_ganho_zera_a_sequencia_de_perdas():
    rm = gerente(config(max_perdas_consecutivas=3, max_trades_dia=10))
    perder(rm, 10.0)
    perder(rm, 10.0)
    ganhar(rm, 5.0)

    assert rm.estado.perdas_consecutivas == 0
    assert rm.avaliar(compra()).allowed is True


def test_trade_zerado_nao_conta_como_perda():
    rm = gerente(config(max_perdas_consecutivas=1, max_trades_dia=10))
    ganhar(rm, 0.0)  # resultado exatamente zero

    assert rm.estado.perdas_consecutivas == 0


def test_custos_podem_transformar_trade_neutro_em_perda():
    rm = gerente(config(custo_por_trade=5.0, max_trades_dia=10))
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    trade = rm.fechar("PETR4", 10.0)  # saiu no mesmo preco

    assert trade.resultado_bruto == pytest.approx(0.0)
    assert trade.resultado == pytest.approx(-5.0)
    assert trade.perdeu is True
    assert rm.estado.perdas_consecutivas == 1


# --- drawdown ---------------------------------------------------------------------


def test_drawdown_maximo_bloqueia():
    rm = gerente(config(capital=10_000.0, drawdown_max_pct=10.0, perda_max_diaria_pct=100.0,
                        max_trades_dia=50, max_perdas_consecutivas=50))
    perder(rm, 1_000.0)

    assert rm.estado.drawdown == pytest.approx(1_000.0)
    assert rm.estado.drawdown_pct == pytest.approx(10.0)
    assert rm.avaliar(compra()).allowed is False


def test_drawdown_e_medido_a_partir_do_pico_e_nao_do_capital_inicial():
    rm = gerente(config(capital=10_000.0, drawdown_max_pct=10.0, perda_max_diaria_pct=100.0,
                        max_trades_dia=50, max_perdas_consecutivas=50))
    ganhar(rm, 2_000.0)  # pico vai para 12.000
    perder(rm, 500.0)

    assert rm.estado.pico == pytest.approx(12_000.0)
    assert rm.estado.drawdown == pytest.approx(500.0)
    assert rm.estado.drawdown_pct == pytest.approx(500 / 12_000 * 100)


def test_drawdown_atravessa_o_pregao():
    rm = gerente(config(capital=10_000.0, drawdown_max_pct=10.0, perda_max_diaria_pct=100.0,
                        max_trades_dia=50, max_perdas_consecutivas=50))
    perder(rm, 1_000.0)
    rm.novo_pregao(date(2026, 8, 21))

    assert rm.estado.drawdown == pytest.approx(1_000.0)
    assert rm.avaliar(compra()).allowed is False  # kill switch de drawdown nao e' diario


# --- kill switch --------------------------------------------------------------------


def test_kill_switch_manual_bloqueia_tudo():
    rm = gerente()
    rm.acionar_kill_switch("noticia bomba no meio do pregao")

    d = rm.avaliar(compra())
    assert d.allowed is False
    assert MotivoRejeicao.KILL_SWITCH.value in d.codigos
    assert "noticia bomba" in d.reason


def test_kill_switch_manual_so_libera_manualmente():
    rm = gerente()
    rm.acionar_kill_switch()
    rm.novo_pregao(date(2026, 8, 21))
    assert rm.avaliar(compra()).allowed is False

    rm.liberar_kill_switch()
    assert rm.avaliar(compra()).allowed is True


def test_kill_switch_arma_sozinho_na_perda_diaria():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0, max_trades_dia=50))
    perder(rm, 300.0)

    assert rm.estado.kill_switch is not None
    assert rm.estado.kill_switch.codigo == "perda_diaria"
    assert rm.estado.kill_switch.diario is True


def test_kill_switch_diario_desarma_no_novo_pregao():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0, max_trades_dia=50))
    perder(rm, 300.0)
    assert rm.liberado is False

    rm.novo_pregao(date(2026, 8, 21))
    assert rm.estado.kill_switch is None
    assert rm.liberado is True


def test_kill_switch_de_drawdown_nao_desarma_sozinho():
    rm = gerente(config(capital=10_000.0, drawdown_max_pct=5.0, perda_max_diaria_pct=100.0,
                        max_trades_dia=50, max_perdas_consecutivas=50))
    perder(rm, 500.0)

    assert rm.estado.kill_switch.codigo == "drawdown"
    assert rm.estado.kill_switch.diario is False
    rm.novo_pregao(date(2026, 8, 21))
    assert rm.estado.kill_switch is not None


def test_kill_switch_arma_nas_perdas_consecutivas():
    rm = gerente(config(max_perdas_consecutivas=2, max_trades_dia=50))
    perder(rm, 10.0)
    perder(rm, 10.0)

    assert rm.estado.kill_switch.codigo == "perdas_consecutivas"


def test_kill_switch_vem_antes_dos_outros_motivos():
    rm = gerente(config(capital=10_000.0, max_trades_dia=1))
    rm.abrir(rm.avaliar(compra()))
    rm.acionar_kill_switch("prioridade")

    d = rm.avaliar(compra(symbol="VALE3"))
    assert d.codigos[0] == MotivoRejeicao.KILL_SWITCH.value


# --- fechamento e contabilidade ---------------------------------------------------


def test_fechar_atualiza_patrimonio_pico_e_resultado_do_dia():
    rm = gerente(config(capital=10_000.0))
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    trade = rm.fechar("PETR4", 10.5)

    esperado = trade.quantidade * 0.5
    assert rm.estado.pnl_dia == pytest.approx(esperado)
    assert rm.estado.patrimonio == pytest.approx(10_000.0 + esperado)
    assert rm.estado.pico == pytest.approx(rm.estado.patrimonio)
    assert "PETR4" not in rm.estado.posicoes


def test_venda_ganha_quando_o_preco_cai():
    rm = gerente(config(capital=10_000.0))
    from cashinho.core.risk import PedidoOperacao

    d = rm.avaliar(PedidoOperacao("PETR4", Direction.SHORT, 10.0, 10.5))
    rm.abrir(d)
    trade = rm.fechar("PETR4", 9.5)

    assert trade.resultado > 0


def test_fechar_ativo_sem_posicao_e_erro():
    with pytest.raises(KeyError):
        gerente().fechar("PETR4", 10.0)


def test_novo_pregao_preserva_patrimonio_pico_e_sequencia_de_perdas():
    rm = gerente(config(capital=10_000.0, max_trades_dia=50, max_perdas_consecutivas=50))
    perder(rm, 100.0)
    patrimonio, pico, seguidas = rm.estado.patrimonio, rm.estado.pico, rm.estado.perdas_consecutivas

    rm.novo_pregao(date(2026, 8, 21))

    assert rm.estado.pnl_dia == 0.0
    assert rm.estado.trades_dia == 0
    assert rm.estado.patrimonio == patrimonio
    assert rm.estado.pico == pico
    assert rm.estado.perdas_consecutivas == seguidas
    assert rm.estado.capital_pregao == patrimonio
