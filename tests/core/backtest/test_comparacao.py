"""Comparar Timeframes: a mesma estrategia em varias escalas, avaliada com equilibrio."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.backtest import BacktestConfig, ModeloCustos
from cashinho.core.backtest.comparacao import (
    PADRAO,
    TIMEFRAMES_PADRAO,
    CriteriosComparacao,
    LinhaComparacao,
    StatusTimeframe,
    avaliar,
    comparar,
    elegibilidade,
    escala,
    fator_confianca,
    pontuar,
)
from cashinho.core.backtest.models import BacktestResult, Metricas
from cashinho.core.risk import RiskConfig

from .factories import ABERTURA, EstrategiaNoCandle, serie_1m

SEM_ATRITO = ModeloCustos(spread_ticks=0.0, slippage_ticks=0.0, taxas_b3_pct=0.0)


def _config(**campos) -> BacktestConfig:
    base = dict(
        symbol="PETR4", timeframe_base="1m", capital_inicial=100_000.0, custos=SEM_ATRITO,
        risco=RiskConfig(capital=100_000.0, max_trades_dia=50, max_perdas_consecutivas=50,
                         perda_max_diaria_pct=100.0),
    )
    base.update(campos)
    return BacktestConfig(**base)


def _serie(n=400):
    return serie_1m([30.0] * n, aberturas=[30.0] * n, maximas=[30.6] * n, minimas=[29.9] * n)


def _resultado(**metricas) -> BacktestResult:
    """BacktestResult sintetico: permite testar a nota sem rodar o engine."""
    padrao = dict(retorno_total=1_000.0, retorno_total_pct=1.0, n_trades=30,
                  max_drawdown=500.0, max_drawdown_pct=0.5, profit_factor=1.8,
                  sharpe=1.5, expectancy_em_r=0.3, custos_totais=100.0, dias=30)
    padrao.update(metricas)
    m = Metricas(**padrao)
    return BacktestResult(
        symbol="PETR4", timeframe="5m", estrategia="teste", capital_inicial=100_000.0,
        capital_final=100_000.0 + m.retorno_total, inicio=ABERTURA, fim=ABERTURA,
        metricas=m, sinais_avaliados=100,
    )


# ---------------------------------------------------------------------------
# execucao
# ---------------------------------------------------------------------------


def test_roda_a_mesma_estrategia_em_todos_os_timeframes():
    comp = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                    _config(), timeframes=["1m", "5m", "15m"])

    assert [l.timeframe for l in comp.linhas] == ["1m", "5m", "15m"]
    assert comp.symbol == "PETR4"


def test_a_lista_padrao_cobre_os_seis_timeframes_pedidos():
    assert TIMEFRAMES_PADRAO == ("1m", "5m", "15m", "30m", "60m", "1d")


def test_so_o_timeframe_muda_entre_as_rodadas():
    """Capital, custos e limites de risco sao os mesmos - senao nao e' comparacao."""
    config = _config(capital_inicial=50_000.0)
    comp = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                    config, timeframes=["1m", "5m"])

    for linha in comp.rodadas:
        assert linha.resultado.capital_inicial == 50_000.0
    assert comp.capital_inicial == 50_000.0


def _serie_5m(n=200):
    from cashinho.models import Candle, Series

    return Series("PETR4", "5m", [
        Candle(ABERTURA + timedelta(minutes=5 * i), 30.0, 30.6, 29.9, 30.0, 10_000.0)
        for i in range(n)
    ])


def test_timeframe_menor_que_a_execucao_e_marcado_como_nao_aplicavel():
    """Pedir 1m com execucao em 5m nao tem como funcionar - e nao derruba o resto."""
    comp = comparar(lambda: EstrategiaNoCandle(31), _serie_5m(),
                    _config(timeframe_base="5m"), timeframes=["1m", "5m"])

    linha = comp.linhas[0]
    assert linha.status is StatusTimeframe.NAO_APLICAVEL
    assert "multiplo" in linha.motivo
    assert linha.resultado is None
    assert comp.linhas[1].status.rodou  # o 5m rodou normalmente


def test_erro_do_motor_em_uma_escala_nao_derruba_a_comparacao():
    """Serie em 1m com execucao configurada em 5m: o motor recusa aquela rodada."""
    comp = comparar(lambda: EstrategiaNoCandle(31), _serie(),
                    _config(timeframe_base="5m"), timeframes=["5m", "15m"])

    assert all(l.status is StatusTimeframe.NAO_APLICAVEL for l in comp.linhas)
    assert all("base" in l.motivo for l in comp.linhas)
    assert "nenhum timeframe" in comp.veredito


def test_timeframe_sem_candles_suficientes_nao_vira_zero_falso():
    """1d numa serie de um pregao nao tem candle fechado: isso e' 'sem sinais'."""
    comp = comparar(lambda: EstrategiaNoCandle(31), _serie(n=100), _config(),
                    timeframes=["1d"])

    linha = comp.linhas[0]
    assert linha.status is StatusTimeframe.SEM_SINAIS
    assert linha.elegivel is False
    assert linha.score == 0.0


def test_timeframe_que_avalia_mas_nao_aciona_fica_sem_trades():
    comp = comparar(lambda: EstrategiaNoCandle(10_000), _serie(), _config(),
                    timeframes=["5m"])

    linha = comp.linhas[0]
    assert linha.status is StatusTimeframe.SEM_TRADES
    assert linha.score == 0.0
    assert linha.elegivel is False
    assert "nenhum trade executado" in linha.ressalvas


def test_comparacao_e_reproduzivel():
    a = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(), _config(),
                 timeframes=["1m", "5m"])
    b = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(), _config(),
                 timeframes=["1m", "5m"])

    assert a.para_dict() == b.para_dict()


# ---------------------------------------------------------------------------
# a nota
# ---------------------------------------------------------------------------


def test_pesos_precisam_somar_um():
    with pytest.raises(ValueError, match="somar"):
        CriteriosComparacao(pesos={"retorno sobre drawdown": 0.5, "sharpe": 0.2})


def test_escala_e_absoluta_e_saturada():
    assert escala(0.0, 0.0, 2.0) == 0.0
    assert escala(1.0, 0.0, 2.0) == 0.5
    assert escala(5.0, 0.0, 2.0) == 1.0  # satura
    assert escala(-3.0, 0.0, 2.0) == 0.0
    assert escala(None, 0.0, 2.0) == 0.0


def test_a_nota_de_um_timeframe_nao_depende_dos_concorrentes():
    """Escala absoluta: o mesmo resultado tira a mesma nota sozinho ou em grupo."""
    sozinho = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                       _config(), timeframes=["5m"])
    acompanhado = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                           _config(), timeframes=["1m", "5m", "15m"])

    nota_sozinho = sozinho.linhas[0].score
    nota_no_grupo = next(l for l in acompanhado.linhas if l.timeframe == "5m").score
    assert nota_sozinho == nota_no_grupo


def test_confianca_cresce_com_a_amostra_e_satura():
    assert fator_confianca(0) == 0.0
    assert fator_confianca(30) == pytest.approx(1.0)
    assert fator_confianca(120) == pytest.approx(1.0)  # satura
    assert fator_confianca(1) < fator_confianca(10) < fator_confianca(30)


def test_um_unico_trade_vencedor_nao_ganha_da_amostra_grande():
    """O caso que motiva o fator de confianca: metricas perfeitas com n=1."""
    sortudo = _resultado(n_trades=1, retorno_total=2_000.0, retorno_total_pct=2.0,
                         max_drawdown=0.0, max_drawdown_pct=0.0, profit_factor=None,
                         sharpe=None, expectancy_em_r=2.0, custos_totais=10.0)
    solido = _resultado(n_trades=40, retorno_total=1_500.0, retorno_total_pct=1.5,
                        max_drawdown=600.0, max_drawdown_pct=0.6, profit_factor=1.6,
                        sharpe=1.4, expectancy_em_r=0.25, custos_totais=300.0)

    nota_sortudo = pontuar(avaliar(sortudo), sortudo.metricas.n_trades)
    nota_solido = pontuar(avaliar(solido), solido.metricas.n_trades)

    assert nota_sortudo < nota_solido
    assert elegibilidade(sortudo)[0] is False  # nem chega a concorrer


def test_retorno_maior_com_risco_muito_pior_perde():
    agressivo = _resultado(n_trades=40, retorno_total=8_000.0, retorno_total_pct=8.0,
                           max_drawdown=6_000.0, max_drawdown_pct=6.0, profit_factor=1.1,
                           sharpe=0.4, expectancy_em_r=0.05, custos_totais=2_000.0)
    equilibrado = _resultado(n_trades=40, retorno_total=3_000.0, retorno_total_pct=3.0,
                             max_drawdown=800.0, max_drawdown_pct=0.8, profit_factor=1.9,
                             sharpe=1.8, expectancy_em_r=0.35, custos_totais=300.0)

    assert pontuar(avaliar(agressivo), 40) < pontuar(avaliar(equilibrado), 40)


def test_custos_que_comem_o_lucro_derrubam_a_nota():
    caro = _resultado(custos_totais=3_000.0, retorno_total=200.0)
    barato = _resultado(custos_totais=100.0, retorno_total=200.0)

    nota_caro = next(n for n in avaliar(caro) if n.nome == "peso dos custos")
    nota_barato = next(n for n in avaliar(barato) if n.nome == "peso dos custos")
    assert nota_caro.nota < nota_barato.nota


def test_metricas_indefinidas_valem_zero_e_nao_nota_cheia():
    """Sem Sharpe e sem profit factor, o criterio nao pode ser premiado."""
    notas = {n.nome: n for n in avaliar(_resultado(sharpe=None, profit_factor=None))}

    assert notas["sharpe"].nota == 0.0
    assert notas["profit factor"].nota == 0.0
    assert "sem dados" in notas["sharpe"].detalhe


# ---------------------------------------------------------------------------
# elegibilidade e veredito
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metricas,trecho",
    [
        ({"retorno_total": -100.0}, "retorno nao positivo"),
        ({"n_trades": 3}, "amostra insuficiente"),
        ({"max_drawdown_pct": 30.0}, "drawdown"),
        ({"profit_factor": 0.8}, "profit factor"),
    ],
)
def test_cortes_duros_reprovam_o_timeframe(metricas, trecho):
    elegivel, ressalvas = elegibilidade(_resultado(**metricas))

    assert elegivel is False
    assert any(trecho in r for r in ressalvas)


def test_amostra_pequena_mas_valida_vira_ressalva_e_nao_reprovacao():
    elegivel, ressalvas = elegibilidade(_resultado(n_trades=15))

    assert elegivel is True
    assert any("amostra ainda pequena" in r for r in ressalvas)


def test_sem_nenhum_elegivel_a_comparacao_nao_escolhe_ninguem():
    comp = comparar(lambda: EstrategiaNoCandle(31, stop=29.9, alvo=30.05), _serie(),
                    _config(), timeframes=["1m", "5m"])

    if not comp.elegiveis:
        assert comp.melhor_equilibrio is None
        assert "nenhum timeframe passou" in comp.veredito or "nenhum timeframe pode" in comp.veredito


def test_melhor_retorno_e_reportado_mesmo_quando_reprovado():
    """O contraponto precisa aparecer - e' o que mostra o custo do risco."""
    comp = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                    _config(), timeframes=["1m", "5m", "15m"])

    if comp.rodadas:
        assert comp.melhor_retorno is not None
        assert comp.melhor_retorno.retorno_pct == max(
            l.retorno_pct for l in comp.rodadas if l.retorno_pct is not None
        )


def test_divergencia_entre_retorno_e_equilibrio_e_sinalizada():
    linhas = [
        LinhaComparacao("5m", StatusTimeframe.OK, resultado=_resultado(
            n_trades=40, retorno_total=8_000.0, retorno_total_pct=8.0, max_drawdown_pct=20.0),
            score=30.0, elegivel=True),
        LinhaComparacao("15m", StatusTimeframe.OK, resultado=_resultado(
            n_trades=40, retorno_total=3_000.0, retorno_total_pct=3.0, max_drawdown_pct=1.0),
            score=80.0, elegivel=True),
    ]
    from cashinho.core.backtest.comparacao import ComparacaoTimeframes

    comp = ComparacaoTimeframes("PETR4", "teste", 100_000.0, linhas)

    assert comp.melhor_equilibrio.timeframe == "15m"
    assert comp.melhor_retorno.timeframe == "5m"
    assert comp.divergem is True
    assert "nao compensa o risco" in comp.veredito


def test_criterios_sao_configuraveis():
    exigente = CriteriosComparacao(min_trades=100)
    assert elegibilidade(_resultado(n_trades=40), exigente)[0] is False

    frouxo = CriteriosComparacao(min_trades=1)
    assert elegibilidade(_resultado(n_trades=40), frouxo)[0] is True


def test_comparacao_serializa_para_a_interface():
    import json

    comp = comparar(lambda: EstrategiaNoCandle(31, stop=29.0, alvo=31.0), _serie(),
                    _config(), timeframes=["1m", "5m"])
    dados = comp.para_dict()
    texto = json.dumps(dados)

    assert dados["symbol"] == "PETR4"
    assert len(dados["linhas"]) == 2
    assert "veredito" in dados and "pesos" in dados
    assert '"score"' in texto
