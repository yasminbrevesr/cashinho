"""As metricas, com numeros conferidos na mao."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest

from cashinho.core.backtest import calcular, max_drawdown, retornos_diarios, sharpe, sortino
from cashinho.core.backtest.models import BacktestTrade, MotivoSaida, PontoEquity
from cashinho.models import Direction

from .factories import ABERTURA


def _trade(resultado: float, custos: float = 0.0, risco: float = 100.0, i: int = 0) -> BacktestTrade:
    """Trade sintetico com resultado liquido exato (100 acoes, R$ 1 = R$ 100)."""
    entrada = 30.0
    saida = entrada + (resultado + custos) / 100.0
    return BacktestTrade(
        symbol="PETR4", direcao=Direction.LONG, quantidade=100,
        entrada_em=ABERTURA + timedelta(minutes=i), entrada_preco=entrada,
        saida_em=ABERTURA + timedelta(minutes=i + 10), saida_preco=saida,
        motivo=MotivoSaida.ALVO, custos=custos, stop=29.0, alvo=31.0, risco_planejado=risco,
    )


def _equity(valores, por_dia: bool = False):
    passo = timedelta(days=1) if por_dia else timedelta(minutes=1)
    return [
        PontoEquity(ABERTURA + passo * i, v, v, 0.0, 0.0, False)
        for i, v in enumerate(valores)
    ]


# --- contagem e taxas ------------------------------------------------------------


def test_contagem_win_rate_e_loss_rate():
    trades = [_trade(100), _trade(200), _trade(-50), _trade(0)]
    m = calcular(trades, _equity([100_000, 100_250]), 100_000)

    assert m.n_trades == 4
    assert m.vencedores == 2 and m.perdedores == 1 and m.empates == 1
    assert m.win_rate == pytest.approx(0.5)
    assert m.loss_rate == pytest.approx(0.25)


def test_payoff_e_a_razao_entre_ganho_e_perda_medios():
    trades = [_trade(300), _trade(100), _trade(-100)]
    m = calcular(trades, _equity([100_000, 100_300]), 100_000)

    assert m.ganho_medio == pytest.approx(200.0)
    assert m.perda_media == pytest.approx(100.0)
    assert m.payoff == pytest.approx(2.0)


def test_expectancy_e_o_resultado_esperado_por_trade():
    trades = [_trade(200), _trade(200), _trade(-100), _trade(-100)]
    m = calcular(trades, _equity([100_000, 100_200]), 100_000)

    # 50% x 200 - 50% x 100 = 50
    assert m.expectancy == pytest.approx(50.0)
    assert m.expectancy_em_r == pytest.approx(0.5)  # risco de 100 por trade


def test_profit_factor_e_a_razao_entre_ganhos_e_perdas_totais():
    trades = [_trade(300), _trade(100), _trade(-200)]
    m = calcular(trades, _equity([100_000, 100_200]), 100_000)

    assert m.profit_factor == pytest.approx(2.0)


def test_profit_factor_e_payoff_ficam_none_sem_perdas():
    """Sem perda a razao seria infinita: melhor dizer 'nao da' do que inventar."""
    m = calcular([_trade(100), _trade(50)], _equity([100_000, 100_150]), 100_000)

    assert m.profit_factor is None
    assert m.payoff is None


def test_sequencias_de_ganhos_e_perdas():
    trades = [_trade(10), _trade(10), _trade(-10), _trade(-10), _trade(-10), _trade(10)]
    m = calcular(trades, _equity([100_000]), 100_000)

    assert m.maior_sequencia_ganhos == 2
    assert m.maior_sequencia_perdas == 3


def test_custos_sao_somados():
    m = calcular([_trade(100, custos=15.0), _trade(-50, custos=15.0)], _equity([100_000]), 100_000)
    assert m.custos_totais == pytest.approx(30.0)


# --- drawdown ------------------------------------------------------------------------


def test_max_drawdown_mede_do_pico_ao_vale():
    equity = _equity([100_000, 110_000, 95_000, 105_000])
    valor, pct = max_drawdown(equity, 100_000)

    assert valor == pytest.approx(15_000.0)
    assert pct == pytest.approx(15_000 / 110_000 * 100)


def test_curva_sempre_subindo_nao_tem_drawdown():
    valor, pct = max_drawdown(_equity([100_000, 101_000, 102_000]), 100_000)
    assert valor == 0.0 and pct == 0.0


def test_drawdown_conta_a_partir_do_capital_inicial():
    """Cair logo no comeco e' drawdown, mesmo sem pico anterior na curva."""
    valor, _ = max_drawdown(_equity([99_000, 98_000]), 100_000)
    assert valor == pytest.approx(2_000.0)


# --- retornos diarios, sharpe e sortino -------------------------------------------------


def test_retornos_diarios_usam_o_ultimo_ponto_de_cada_dia():
    equity = _equity([100_000, 101_000, 102_000], por_dia=True)
    retornos = retornos_diarios(equity, 100_000)

    assert len(retornos) == 3
    assert retornos[1] == pytest.approx(0.01)


def test_sharpe_e_media_sobre_desvio_anualizado():
    retornos = [0.01, -0.005, 0.02, 0.0]
    media = sum(retornos) / 4
    desvio = math.sqrt(sum((r - media) ** 2 for r in retornos) / 3)

    assert sharpe(retornos) == pytest.approx(media / desvio * math.sqrt(252))


def test_sortino_ignora_a_volatilidade_de_alta():
    """Duas series com a mesma media: a que so oscila para cima tem Sortino maior."""
    calmo = [0.01, 0.005, 0.015, 0.01]
    turbulento = [0.04, -0.02, 0.03, -0.01]

    assert sortino(calmo) is None or sortino(calmo) > (sortino(turbulento) or 0)


def test_sharpe_e_sortino_ficam_none_sem_dados_suficientes():
    assert sharpe([]) is None
    assert sharpe([0.01]) is None
    assert sortino([0.01]) is None
    assert sharpe([0.01, 0.01, 0.01]) is None  # desvio zero
    assert sortino([0.01, 0.02]) is None  # nenhum dia negativo


# --- exposicao ----------------------------------------------------------------------------


def test_exposicao_mede_o_tempo_com_posicao():
    pontos = [
        PontoEquity(ABERTURA + timedelta(minutes=i), 100_000, 100_000, 0.0,
                    30_000.0 if i < 4 else 0.0, i < 4)
        for i in range(10)
    ]
    m = calcular([], pontos, 100_000)

    assert m.exposicao_tempo_pct == pytest.approx(40.0)
    assert m.exposicao_media_pct == pytest.approx(12.0)  # 30 mil em 4 de 10 pontos


# --- casos de borda -------------------------------------------------------------------------


def test_sem_trades_e_sem_curva_nao_quebra():
    m = calcular([], [], 100_000)

    assert m.n_trades == 0
    assert m.retorno_total == 0.0
    assert m.win_rate == 0.0
    assert m.payoff is None and m.profit_factor is None
    assert m.sharpe is None and m.sortino is None


def test_retorno_total_vem_da_curva_e_nao_da_soma_dos_trades():
    """A curva inclui a posicao aberta marcada a mercado; a soma dos trades, nao."""
    m = calcular([_trade(100)], _equity([100_000, 100_400]), 100_000)

    assert m.retorno_total == pytest.approx(400.0)
    assert m.retorno_total_pct == pytest.approx(0.4)
