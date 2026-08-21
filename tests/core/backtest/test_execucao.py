"""Mecanica de execucao: stop, alvo, gaps, horario e custos."""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from cashinho.core.backtest import BacktestConfig, BacktestEngine, ModeloCustos
from cashinho.core.backtest.models import MotivoSaida
from cashinho.core.risk import RiskConfig
from cashinho.core.strategy.models import Action
from cashinho.models import Direction

from .factories import ABERTURA, EstrategiaNoCandle, EstrategiaNunca, serie_1m

SEM_ATRITO = ModeloCustos(spread_ticks=0.0, slippage_ticks=0.0, taxas_b3_pct=0.0)


def _config(**campos) -> BacktestConfig:
    base = dict(
        symbol="PETR4", timeframe_base="1m", timeframe_setup="1m",
        capital_inicial=100_000.0, custos=SEM_ATRITO,
        risco=RiskConfig(capital=100_000.0, risco_por_trade_pct=1.0, max_trades_dia=20,
                         max_perdas_consecutivas=20, perda_max_diaria_pct=100.0),
    )
    base.update(campos)
    return BacktestConfig(**base)


def _serie(n=60, close=30.0, maxima=30.1, minima=29.9, abertura=30.0):
    return serie_1m([close] * n, aberturas=[abertura] * n,
                    maximas=[maxima] * n, minimas=[minima] * n)


# --- stop e alvo ---------------------------------------------------------------


def test_alvo_atingido_encerra_no_alvo():
    serie = _serie(maxima=31.5)
    resultado = BacktestEngine(EstrategiaNoCandle(31, alvo=31.0, stop=29.0), _config()).rodar(serie)

    trade = resultado.trades[0]
    assert trade.motivo is MotivoSaida.ALVO
    assert trade.saida_preco == pytest.approx(31.0)
    assert trade.venceu


def test_stop_acionado_encerra_no_stop():
    serie = _serie(minima=28.5)
    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=40.0), _config()).rodar(serie)

    trade = resultado.trades[0]
    assert trade.motivo is MotivoSaida.STOP
    assert trade.saida_preco == pytest.approx(29.0)
    assert trade.perdeu


def test_gap_alem_do_stop_executa_na_abertura_e_nao_no_stop():
    """Abriu com gap abaixo do stop: quem for stopado leva o preco da abertura."""
    closes = [30.0] * 60
    aberturas = [30.0] * 60
    aberturas[32] = 28.0  # gap
    minimas = [29.9] * 60
    minimas[32] = 27.5
    serie = serie_1m(closes, aberturas=aberturas, maximas=[30.1] * 60, minimas=minimas)

    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=40.0), _config()).rodar(serie)
    trade = resultado.trades[0]

    assert trade.motivo is MotivoSaida.STOP
    assert trade.saida_preco == pytest.approx(28.0)  # a abertura, pior que o stop


def test_gap_alem_do_alvo_executa_na_abertura_a_favor():
    closes = [30.0] * 60
    aberturas = [30.0] * 60
    aberturas[32] = 32.0
    maximas = [30.1] * 60
    maximas[32] = 32.5
    serie = serie_1m(closes, aberturas=aberturas, maximas=maximas, minimas=[29.9] * 60)

    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _config()).rodar(serie)
    trade = resultado.trades[0]

    assert trade.motivo is MotivoSaida.ALVO
    assert trade.saida_preco == pytest.approx(32.0)


def test_stop_e_alvo_no_mesmo_candle_assume_o_stop_por_padrao():
    """Sem tick a tick nao da para saber a ordem: o engine assume o pior."""
    serie = _serie(maxima=31.5, minima=28.5)
    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _config()).rodar(serie)

    assert resultado.trades[0].motivo is MotivoSaida.STOP


def test_prioridade_intracandle_e_configuravel():
    serie = _serie(maxima=31.5, minima=28.5)
    otimista = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0),
                              _config(prioridade_intracandle="alvo")).rodar(serie)
    assert otimista.trades[0].motivo is MotivoSaida.ALVO

    indeciso = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0),
                              _config(prioridade_intracandle="nenhuma")).rodar(serie)
    assert indeciso.trades[0].motivo is MotivoSaida.FIM_DO_DIA  # segurou ate o fim


def test_posicao_pode_ser_stopada_no_mesmo_candle_da_entrada():
    closes = [30.0] * 60
    minimas = [29.9] * 60
    minimas[31] = 28.0  # o proprio candle de entrada perfura o stop
    serie = serie_1m(closes, aberturas=[30.0] * 60, maximas=[30.1] * 60, minimas=minimas)

    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=40.0), _config()).rodar(serie)
    trade = resultado.trades[0]

    assert trade.entrada_em == trade.saida_em
    assert trade.motivo is MotivoSaida.STOP


# --- venda a descoberto ----------------------------------------------------------


def test_venda_ganha_quando_o_preco_cai():
    serie = _serie(minima=28.5)
    estrategia = EstrategiaNoCandle(31, action=Action.SELL, entrada=30.0, stop=31.0, alvo=29.0)
    resultado = BacktestEngine(estrategia, _config()).rodar(serie)

    trade = resultado.trades[0]
    assert trade.direcao is Direction.SHORT
    assert trade.motivo is MotivoSaida.ALVO
    assert trade.venceu


def test_venda_pode_ser_desligada():
    serie = _serie(minima=28.5)
    estrategia = EstrategiaNoCandle(31, action=Action.SELL, entrada=30.0, stop=31.0, alvo=29.0)
    resultado = BacktestEngine(estrategia, _config(permitir_venda=False)).rodar(serie)

    assert resultado.trades == []


# --- horario ------------------------------------------------------------------------


def test_posicao_e_zerada_no_horario_configurado():
    serie = serie_1m([30.0] * 460, aberturas=[30.0] * 460,
                     maximas=[30.1] * 460, minimas=[29.9] * 460)
    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=20.0, alvo=40.0),
                               _config(fechar_em=time(11, 0))).rodar(serie)

    trade = resultado.trades[0]
    assert trade.motivo is MotivoSaida.FIM_DO_DIA
    assert trade.saida_em.time() == time(11, 0)


def test_nenhuma_posicao_atravessa_a_noite():
    """Dois pregoes: o trade do primeiro dia fecha no primeiro dia."""
    dia1 = serie_1m([30.0] * 300, aberturas=[30.0] * 300, maximas=[30.1] * 300, minimas=[29.9] * 300)
    dia2 = serie_1m([30.0] * 300, aberturas=[30.0] * 300, maximas=[30.1] * 300,
                    minimas=[29.9] * 300, inicio=ABERTURA + timedelta(days=1))
    from cashinho.models import Series

    serie = Series("PETR4", "1m", dia1.candles + dia2.candles)
    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=20.0, alvo=40.0), _config()).rodar(serie)

    assert resultado.trades
    for t in resultado.trades:
        assert t.entrada_em.date() == t.saida_em.date()


def test_entradas_param_no_horario_limite():
    serie = serie_1m([30.0] * 460, aberturas=[30.0] * 460,
                     maximas=[30.1] * 460, minimas=[29.9] * 460)
    # sinal as 12:00 (candle 120), mas o limite de entrada e' 11:00
    resultado = BacktestEngine(EstrategiaNoCandle(121, stop=29.0, alvo=31.0),
                               _config(entrada_ate=time(11, 0))).rodar(serie)

    assert resultado.trades == []
    assert resultado.rejeicoes_do_risco.get("fora_do_horario_de_entrada") == 1


# --- custos no resultado ---------------------------------------------------------------


def test_custos_saem_do_resultado_do_trade():
    serie = _serie(maxima=31.5)
    com_custos = ModeloCustos(spread_ticks=2.0, slippage_ticks=1.0, taxas_b3_pct=0.03,
                              corretagem_fixa=5.0)
    resultado = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0),
                               _config(custos=com_custos)).rodar(serie)
    trade = resultado.trades[0]

    assert trade.custos > 0
    assert trade.resultado == pytest.approx(trade.resultado_bruto - trade.custos)
    assert trade.resultado < trade.resultado_bruto


def test_atrito_piora_o_resultado_da_mesma_serie():
    serie = _serie(maxima=31.5)
    limpo = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _config()).rodar(serie)
    sujo = BacktestEngine(
        EstrategiaNoCandle(31, stop=29.0, alvo=31.0),
        _config(custos=ModeloCustos(spread_ticks=4.0, slippage_ticks=2.0, taxas_b3_pct=0.05)),
    ).rodar(serie)

    assert sujo.metricas.retorno_total < limpo.metricas.retorno_total


# --- casos sem trade -------------------------------------------------------------------


def test_estrategia_que_nunca_aciona_nao_gera_trade():
    resultado = BacktestEngine(EstrategiaNunca(), _config()).rodar(_serie())

    assert resultado.trades == []
    assert resultado.metricas.n_trades == 0
    assert resultado.capital_final == pytest.approx(100_000.0)
    assert resultado.metricas.max_drawdown == 0.0


def test_periodo_sem_candles_avisa_em_vez_de_quebrar():
    from datetime import date

    resultado = BacktestEngine(
        EstrategiaNoCandle(31), _config(inicio=date(2027, 1, 1), fim=date(2027, 1, 31))
    ).rodar(_serie())

    assert resultado.trades == []
    assert any("nenhum candle" in a for a in resultado.avisos)


def test_recorte_de_periodo_limita_os_candles():
    from datetime import date
    from cashinho.models import Series

    dia1 = _serie(n=300)
    dia2 = serie_1m([30.0] * 300, aberturas=[30.0] * 300, maximas=[30.1] * 300,
                    minimas=[29.9] * 300, inicio=ABERTURA + timedelta(days=1))
    serie = Series("PETR4", "1m", dia1.candles + dia2.candles)

    resultado = BacktestEngine(
        EstrategiaNunca(), _config(inicio=ABERTURA.date() + timedelta(days=1))
    ).rodar(serie)

    assert all(p.ts.date() == (ABERTURA.date() + timedelta(days=1)) for p in resultado.equity)
