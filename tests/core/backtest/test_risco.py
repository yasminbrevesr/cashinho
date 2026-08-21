"""O Risk Manager mandando no backtest - do sizing ao kill switch."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.backtest import BacktestConfig, BacktestEngine, ModeloCustos
from cashinho.core.backtest.models import MotivoSaida
from cashinho.core.risk import RiskConfig
from cashinho.models import Series

from .factories import ABERTURA, EstrategiaNoCandle, serie_1m

SEM_ATRITO = ModeloCustos(spread_ticks=0.0, slippage_ticks=0.0, taxas_b3_pct=0.0)


def _config(risco: RiskConfig, **campos) -> BacktestConfig:
    base = dict(symbol="PETR4", timeframe_base="1m", timeframe_setup="1m",
                capital_inicial=risco.capital, custos=SEM_ATRITO, risco=risco)
    base.update(campos)
    return BacktestConfig(**base)


def _serie(n=200, **kwargs):
    padrao = dict(aberturas=[30.0] * n, maximas=[30.1] * n, minimas=[29.9] * n)
    padrao.update(kwargs)
    return serie_1m([30.0] * n, **padrao)


def test_quantidade_vem_do_risco_e_nao_da_estrategia():
    """1% de 100 mil = R$ 1.000 de risco; stop a R$ 1,00 -> 1.000 acoes."""
    risco = RiskConfig(capital=100_000.0, risco_por_trade_pct=1.0,
                       exposicao_max_por_ativo_pct=100.0, exposicao_max_total_pct=100.0)
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.0, alvo=40.0), _config(risco)
    ).rodar(_serie())

    assert resultado.trades[0].quantidade == 1_000


def test_maximo_de_trades_por_dia_limita_a_rodada():
    risco = RiskConfig(capital=100_000.0, max_trades_dia=2, max_perdas_consecutivas=50,
                       perda_max_diaria_pct=100.0)
    # a estrategia tenta entrar em todo candle a partir do 31
    serie = _serie(n=300, minimas=[29.0] * 300)  # stop bate sempre
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.5, alvo=40.0, repetir=True), _config(risco)
    ).rodar(serie)

    assert len(resultado.trades) == 2
    assert resultado.rejeicoes_do_risco.get("maximo_de_trades", 0) > 0


def test_perda_diaria_arma_o_kill_switch_e_para_o_dia():
    risco = RiskConfig(capital=10_000.0, risco_por_trade_pct=2.0, perda_max_diaria_pct=1.0,
                       max_trades_dia=50, max_perdas_consecutivas=50,
                       exposicao_max_por_ativo_pct=100.0, exposicao_max_total_pct=100.0)
    serie = _serie(n=300, minimas=[28.0] * 300)  # tudo vira stop
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.0, alvo=40.0, repetir=True), _config(risco)
    ).rodar(serie)

    assert resultado.rejeicoes_do_risco.get("kill_switch", 0) > 0
    assert len(resultado.trades) <= 2


def test_contadores_do_risco_reiniciam_a_cada_pregao():
    risco = RiskConfig(capital=100_000.0, max_trades_dia=1, max_perdas_consecutivas=50,
                       perda_max_diaria_pct=100.0)
    dia1 = _serie(n=200)
    dia2 = serie_1m([30.0] * 200, aberturas=[30.0] * 200, maximas=[30.1] * 200,
                    minimas=[29.9] * 200, inicio=ABERTURA + timedelta(days=1))
    serie = Series("PETR4", "1m", dia1.candles + dia2.candles)

    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.0, alvo=40.0, repetir=True), _config(risco)
    ).rodar(serie)

    dias = {t.entrada_em.date() for t in resultado.trades}
    assert len(resultado.trades) == 2  # um por pregao
    assert len(dias) == 2


def test_rejeicoes_do_risco_sao_contabilizadas_por_motivo():
    # R$ 100 de capital com teto de 20% por ativo: R$ 20 nao compram
    # uma acao de R$ 30 - o risco recusa em vez de arredondar para cima
    risco = RiskConfig(capital=100.0, risco_por_trade_pct=1.0, max_trades_dia=50,
                       perda_max_diaria_pct=100.0)
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.99, alvo=40.0, repetir=True), _config(risco)
    ).rodar(_serie())

    assert resultado.trades == []
    assert sum(resultado.rejeicoes_do_risco.values()) > 0
    assert "exposicao_maxima_por_ativo" in resultado.rejeicoes_do_risco


def test_risco_dimensiona_para_baixo_em_vez_de_recusar_quando_da():
    """Com capital apertado, o certo e' comprar menos - nao desistir."""
    risco = RiskConfig(capital=1_000.0, risco_por_trade_pct=1.0, max_trades_dia=50,
                       perda_max_diaria_pct=100.0)
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.99, alvo=40.0), _config(risco)
    ).rodar(_serie())

    assert len(resultado.trades) == 1
    assert 0 < resultado.trades[0].quantidade <= 6  # cabe no teto de 20% do capital


def test_capital_do_backtest_manda_no_capital_do_risco():
    config = BacktestConfig(capital_inicial=250_000.0, risco=RiskConfig(capital=10_000.0))
    assert config.risco.capital == 250_000.0


def test_curva_de_capital_comeca_no_capital_inicial():
    risco = RiskConfig(capital=100_000.0)
    resultado = BacktestEngine(EstrategiaNoCandle(10_000), _config(risco)).rodar(_serie())

    assert resultado.equity[0].equity == pytest.approx(100_000.0)
    assert all(p.posicionado is False for p in resultado.equity)


def test_posicao_aberta_e_marcada_a_mercado_na_curva():
    risco = RiskConfig(capital=100_000.0, exposicao_max_por_ativo_pct=100.0,
                       exposicao_max_total_pct=100.0)
    closes = [30.0] * 100
    closes[40] = 30.5  # com posicao aberta, a curva precisa sentir isso
    serie = serie_1m(closes, aberturas=[30.0] * 100, maximas=[30.6] * 100, minimas=[29.9] * 100)

    resultado = BacktestEngine(
        EstrategiaNoCandle(31, entrada=30.0, stop=29.0, alvo=40.0), _config(risco)
    ).rodar(serie)

    ponto = resultado.equity[40]
    assert ponto.posicionado is True
    assert ponto.aberto > 0
    assert ponto.equity > 100_000.0
