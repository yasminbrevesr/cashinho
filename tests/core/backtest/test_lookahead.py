"""A garantia central do engine: ninguem age antes do candle fechar."""

from __future__ import annotations

import pytest

from cashinho.core.backtest import BacktestConfig, BacktestEngine, ModeloCustos
from cashinho.core.risk import RiskConfig
from cashinho.core.strategy.models import Action

from .factories import EstrategiaNoCandle, serie_1m

SEM_ATRITO = ModeloCustos(spread_ticks=0.0, slippage_ticks=0.0, taxas_b3_pct=0.0)


def _config(**campos) -> BacktestConfig:
    base = dict(
        symbol="PETR4",
        timeframe_base="1m",
        timeframe_setup="1m",
        capital_inicial=100_000.0,
        custos=SEM_ATRITO,
        risco=RiskConfig(capital=100_000.0, risco_por_trade_pct=1.0, max_trades_dia=20,
                         max_perdas_consecutivas=20, perda_max_diaria_pct=100.0),
    )
    base.update(campos)
    return BacktestConfig(**base)


def test_entrada_executa_na_abertura_do_candle_seguinte():
    """Sinal no fechamento do candle 30 -> entrada na ABERTURA do candle 31."""
    closes = [30.0] * 60
    aberturas = [30.0] * 60
    aberturas[31] = 30.55  # so a abertura do candle seguinte e' diferente
    serie = serie_1m(closes, aberturas=aberturas, maximas=[31.0] * 60, minimas=[29.0] * 60)

    estrategia = EstrategiaNoCandle(emitir_em=31, entrada=30.0, stop=29.0, alvo=60.0)
    resultado = BacktestEngine(estrategia, _config()).rodar(serie)

    assert len(resultado.trades) == 1
    trade = resultado.trades[0]
    assert trade.entrada_em == serie.candles[31].ts  # candle seguinte ao sinal
    assert trade.entrada_preco == pytest.approx(30.55)  # a ABERTURA dele


def test_estrategia_nunca_ve_candle_alem_do_instante_avaliado():
    """Cada avaliacao enxerga exatamente os candles ja fechados, nem um a mais."""
    serie = serie_1m([30.0 + i * 0.01 for i in range(80)])
    estrategia = EstrategiaNoCandle(emitir_em=10_000)  # nunca aciona

    BacktestEngine(estrategia, _config()).rodar(serie)

    assert estrategia.avaliacoes
    for tamanho, ultimo_ts in estrategia.avaliacoes:
        # o candle mais recente visto e' o de indice tamanho-1: nunca o seguinte
        assert ultimo_ts == serie.candles[tamanho - 1].ts


def test_avaliacoes_acontecem_uma_vez_por_candle_e_em_ordem():
    serie = serie_1m([30.0] * 50)
    estrategia = EstrategiaNoCandle(emitir_em=10_000)

    BacktestEngine(estrategia, _config()).rodar(serie)

    tamanhos = [t for t, _ in estrategia.avaliacoes]
    assert tamanhos == sorted(tamanhos)
    assert len(tamanhos) == len(set(tamanhos))  # nenhuma reavaliacao do mesmo candle


def test_o_candle_do_sinal_nao_pode_ser_usado_para_entrar():
    """Se o engine entrasse no fechamento do sinal, pegaria o candle inteiro."""
    closes = [30.0] * 60
    # o candle 31 dispara e fecha muito acima: entrar no fechamento de 30
    # capturaria esse movimento inteiro de graca
    closes[31] = 33.0
    aberturas = [30.0] * 60
    aberturas[31] = 30.0
    maximas = [30.1] * 60
    maximas[31] = 33.0
    serie = serie_1m(closes, aberturas=aberturas, maximas=maximas, minimas=[29.9] * 60)

    estrategia = EstrategiaNoCandle(emitir_em=31, entrada=30.0, stop=29.0, alvo=32.0)
    resultado = BacktestEngine(estrategia, _config()).rodar(serie)

    trade = resultado.trades[0]
    assert trade.entrada_preco == pytest.approx(30.0)  # abertura do 31, nao o fechamento
    assert trade.entrada_em == serie.candles[31].ts


def test_sem_candle_seguinte_o_sinal_nao_vira_trade():
    """Sinal no ultimo candle da serie nao tem onde executar."""
    serie = serie_1m([30.0] * 40)
    estrategia = EstrategiaNoCandle(emitir_em=40)  # ultimo candle

    resultado = BacktestEngine(estrategia, _config()).rodar(serie)

    assert resultado.trades == []
    assert resultado.sinais_acionaveis == 1


def test_saida_so_usa_precos_do_candle_corrente():
    """O stop dispara no candle em que a minima o alcanca - nem antes, nem depois."""
    closes = [30.0] * 60
    minimas = [29.9] * 60
    minimas[35] = 29.0  # o unico candle que perfura o stop
    serie = serie_1m(closes, aberturas=[30.0] * 60, maximas=[30.1] * 60, minimas=minimas)

    estrategia = EstrategiaNoCandle(emitir_em=31, entrada=30.0, stop=29.5, alvo=40.0)
    resultado = BacktestEngine(estrategia, _config()).rodar(serie)

    trade = resultado.trades[0]
    assert trade.saida_em == serie.candles[35].ts
    assert trade.saida_preco == pytest.approx(29.5)


def test_resultado_e_reproduzivel():
    serie = serie_1m([30.0 + (i % 7) * 0.05 for i in range(120)])
    a = BacktestEngine(EstrategiaNoCandle(emitir_em=40), _config()).rodar(serie)
    b = BacktestEngine(EstrategiaNoCandle(emitir_em=40), _config()).rodar(serie)

    assert a.para_dict()["trades"] == b.para_dict()["trades"]
    assert a.metricas.para_dict() == b.metricas.para_dict()
