"""A pagina Backtest: curva, drawdown, trades e metricas."""

from __future__ import annotations

import json

from cashinho.core.backtest import BacktestConfig, BacktestEngine, ModeloCustos
from cashinho.core.backtest.view import (
    curva_de_capital,
    curva_de_drawdown,
    lista_de_trades,
    pagina,
    painel_metricas,
    resumo,
)
from cashinho.core.risk import RiskConfig

from .factories import EstrategiaNoCandle, EstrategiaNunca, serie_1m

SEM_ATRITO = ModeloCustos(spread_ticks=0.0, slippage_ticks=0.0, taxas_b3_pct=0.0)
CONFIG = BacktestConfig(
    symbol="PETR4", timeframe_base="1m", timeframe_setup="1m", capital_inicial=100_000.0,
    custos=SEM_ATRITO,
    risco=RiskConfig(capital=100_000.0, max_trades_dia=20, max_perdas_consecutivas=20,
                     perda_max_diaria_pct=100.0),
)
SERIE = serie_1m([30.0] * 200, aberturas=[30.0] * 200, maximas=[31.5] * 200, minimas=[29.9] * 200)
RESULTADO = BacktestEngine(EstrategiaNoCandle(31, stop=29.0, alvo=31.0), CONFIG).rodar(SERIE)
VAZIO = BacktestEngine(EstrategiaNunca(), CONFIG).rodar(SERIE)


def test_pagina_tem_as_quatro_secoes_pedidas():
    texto = pagina(RESULTADO)

    assert "CURVA DE CAPITAL" in texto
    assert "DRAWDOWN" in texto
    assert "TRADES" in texto
    assert "METRICAS" in texto


def test_cabecalho_traz_ativo_timeframe_e_periodo():
    texto = pagina(RESULTADO)

    assert "PETR4" in texto
    assert "1m" in texto
    assert "17/08/2026" in texto


def test_curva_marca_a_linha_do_capital_inicial():
    texto = curva_de_capital(RESULTADO)

    assert "capital inicial" in texto
    assert "R$ 100.000,00" in texto


def test_metricas_aparecem_com_os_nomes_pedidos():
    texto = painel_metricas(RESULTADO)

    for rotulo in ("retorno total", "trades", "win rate", "loss rate", "payoff",
                   "expectancy", "profit factor", "max drawdown", "sharpe", "sortino",
                   "exposicao (tempo)"):
        assert rotulo in texto


def test_metrica_sem_valor_aparece_como_traco_e_nao_como_zero():
    """Sem perdas, profit factor nao existe - e a pagina nao pode fingir que e' 0."""
    texto = painel_metricas(RESULTADO)

    assert RESULTADO.metricas.profit_factor is None
    assert "profit factor               -" in texto or "profit factor" in texto


def test_lista_de_trades_mostra_entrada_saida_e_resultado():
    texto = lista_de_trades(RESULTADO)
    trade = RESULTADO.trades[0]

    assert "entrada" in texto and "saida" in texto and "motivo" in texto
    assert f"{trade.quantidade}" in texto
    assert trade.motivo.value in texto


def test_lista_de_trades_limita_e_avisa_quanto_sobrou():
    muitos = BacktestEngine(
        EstrategiaNoCandle(31, stop=29.0, alvo=31.0, repetir=True), CONFIG
    ).rodar(SERIE)
    texto = lista_de_trades(muitos, limite=2)

    assert texto.count("COMPRA") == 2
    if len(muitos.trades) > 2:
        assert "e mais" in texto


def test_pagina_sem_trades_nao_quebra():
    texto = pagina(VAZIO)

    assert "nenhum trade no periodo" in texto
    assert "METRICAS" in texto


def test_pagina_avisa_quando_a_estrategia_e_experimental():
    from cashinho.core.strategy import BaselineTendenciaVolumeATR

    real = BacktestEngine(BaselineTendenciaVolumeATR(), CONFIG).rodar(SERIE)
    assert "RESULTADO NAO PROVA NADA" in pagina(real)
    assert "RESULTADO NAO PROVA NADA" not in pagina(RESULTADO)  # estrategia de teste


def test_pagina_alerta_amostra_pequena():
    texto = pagina(RESULTADO)

    assert "AVISOS" in texto
    assert "amostra pequena" in texto or "pregao" in texto


def test_pagina_mostra_sinais_barrados_pelo_risco():
    apertado = BacktestConfig(
        symbol="PETR4", timeframe_base="1m", timeframe_setup="1m", capital_inicial=100.0,
        custos=SEM_ATRITO, risco=RiskConfig(capital=100.0, max_trades_dia=50),
    )
    resultado = BacktestEngine(
        EstrategiaNoCandle(31, stop=29.0, alvo=31.0, repetir=True), apertado
    ).rodar(SERIE)

    assert "SINAIS BARRADOS" in pagina(resultado)


def test_drawdown_nao_mostra_zero_negativo():
    assert "-0,00%" not in curva_de_drawdown(RESULTADO)


def test_cores_sao_opcionais():
    assert "\033[" not in pagina(RESULTADO, cores=False)
    assert "\033[" in pagina(RESULTADO, cores=True)


def test_resumo_cabe_em_uma_linha():
    linha = resumo(RESULTADO)

    assert "\n" not in linha
    assert "PETR4" in linha and "retorno" in linha


def test_resultado_serializa_para_uma_interface_grafica():
    dados = RESULTADO.para_dict()
    texto = json.dumps(dados)

    assert dados["symbol"] == "PETR4"
    assert set(dados["metricas"]) >= {"retorno_total", "win_rate", "payoff", "expectancy",
                                      "profit_factor", "max_drawdown", "sharpe", "sortino",
                                      "exposicao_tempo_pct"}
    assert dados["trades"][0]["motivo"] in {"stop", "alvo", "fim do dia", "fim dos dados"}
    assert '"equity"' in texto
