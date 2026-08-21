"""A tela Comparar Timeframes: tabela, graficos e veredito."""

from __future__ import annotations

from cashinho.core.backtest.comparacao import (
    ComparacaoTimeframes,
    LinhaComparacao,
    StatusTimeframe,
    avaliar,
    fator_confianca,
    pontuar,
)
from cashinho.core.backtest.models import BacktestResult, Metricas
from cashinho.core.backtest.view_comparacao import (
    barras,
    dispersao,
    graficos,
    pagina_comparacao,
    painel_notas,
    tabela,
)

from .factories import ABERTURA


def _resultado(**metricas) -> BacktestResult:
    padrao = dict(retorno_total=1_000.0, retorno_total_pct=1.0, n_trades=40,
                  max_drawdown=500.0, max_drawdown_pct=0.5, profit_factor=1.8, sharpe=1.5,
                  win_rate=0.55, loss_rate=0.45, expectancy=25.0, expectancy_em_r=0.3,
                  custos_totais=100.0, dias=30)
    padrao.update(metricas)
    m = Metricas(**padrao)
    return BacktestResult("PETR4", "5m", "teste", 100_000.0, 100_000.0 + m.retorno_total,
                          ABERTURA, ABERTURA, metricas=m, sinais_avaliados=100)


def _linha(tf, elegivel=True, **metricas) -> LinhaComparacao:
    r = _resultado(**metricas)
    notas = avaliar(r)
    return LinhaComparacao(
        timeframe=tf, status=StatusTimeframe.OK, resultado=r, notas=notas,
        score=pontuar(notas, r.metricas.n_trades),
        score_bruto=round(sum(n.contribuicao for n in notas) * 100, 1),
        confianca=fator_confianca(r.metricas.n_trades),
        elegivel=elegivel, ressalvas=[] if elegivel else ["amostra insuficiente (4 trades)"],
    )


COMP = ComparacaoTimeframes(
    symbol="PETR4", estrategia="baseline-tendencia", capital_inicial=100_000.0,
    inicio=ABERTURA, fim=ABERTURA,
    linhas=[
        _linha("1m", elegivel=False, retorno_total=-200.0, retorno_total_pct=-0.2, profit_factor=0.7),
        _linha("5m", retorno_total=3_000.0, retorno_total_pct=3.0, max_drawdown_pct=0.4),
        _linha("15m", elegivel=False, n_trades=4, retorno_total=5_000.0, retorno_total_pct=5.0,
               max_drawdown_pct=8.0),
        LinhaComparacao("1d", StatusTimeframe.SEM_SINAIS, motivo="sem candle fechado"),
    ],
)


def test_tabela_traz_as_oito_metricas_pedidas():
    texto = tabela(COMP)

    for coluna in ("trades", "retorno", "drawdown", "PF", "sharpe", "win", "expect.", "custos"):
        assert coluna in texto


def test_tabela_tem_uma_linha_por_timeframe():
    texto = tabela(COMP)

    for tf in ("1m", "5m", "15m", "1d"):
        assert tf in texto


def test_tabela_marca_o_recomendado_e_explica_os_reprovados():
    texto = tabela(COMP)

    assert "RECOMENDADO" in texto
    assert "reprovado" in texto
    assert "sem sinais" in texto


def test_graficos_cobrem_retorno_drawdown_e_nota():
    texto = graficos(COMP)

    assert "RETORNO (%)" in texto
    assert "MAX DRAWDOWN (%)" in texto
    assert "NOTA DE EQUILIBRIO" in texto


def test_barras_lidam_com_valores_negativos_e_marcam_o_zero():
    texto = barras("teste", [("1m", -1.5), ("5m", 3.0)])

    assert "zero" in texto
    assert "-1,50" in texto and "3,00" in texto


def test_barras_escrevem_o_valor_na_ponta():
    """Em terminal nao existe tooltip: o numero precisa estar visivel."""
    texto = barras("teste", [("5m", 2.0)])

    assert "2,00" in texto


def test_barras_sem_dados_avisam():
    assert "sem dados" in barras("teste", [("5m", None)])


def test_dispersao_usa_um_eixo_para_cada_grandeza():
    texto = dispersao(COMP)

    assert "RISCO x RETORNO" in texto
    assert "drawdown maximo" in texto
    assert "●" in texto
    for tf in ("1m", "5m", "15m"):
        assert tf in texto


def test_pagina_mostra_o_veredito_e_o_criterio():
    texto = pagina_comparacao(COMP)

    assert "VEREDITO" in texto
    assert "maior retorno, sozinho, nao elege timeframe nenhum" in texto


def test_pagina_explica_como_a_nota_foi_formada():
    texto = pagina_comparacao(COMP)

    assert "CHEGOU A NOTA" in texto
    assert "confianca da amostra" in texto
    assert "nota bruta" in texto


def test_pagina_lista_por_que_os_outros_nao_passaram():
    texto = pagina_comparacao(COMP)

    assert "POR QUE OS OUTROS NAO PASSARAM" in texto
    assert "amostra insuficiente" in texto


def test_pagina_deixa_claro_que_so_o_timeframe_muda():
    texto = pagina_comparacao(COMP)

    assert "so o timeframe muda" in texto


def test_pagina_sem_nenhum_aprovado_diz_isso():
    vazio = ComparacaoTimeframes(
        symbol="PETR4", estrategia="teste", capital_inicial=100_000.0,
        linhas=[_linha("5m", elegivel=False, retorno_total=-500.0, retorno_total_pct=-0.5)],
    )
    texto = pagina_comparacao(vazio)

    assert "nenhum timeframe passou" in texto
    assert "CHEGOU A NOTA" not in texto  # nao ha vencedor para detalhar


def test_painel_de_notas_mostra_peso_e_detalhe_de_cada_criterio():
    texto = painel_notas(COMP.melhor_equilibrio)

    assert "retorno sobre drawdown" in texto
    assert "peso 0.25" in texto
    assert "alvo" in texto


def test_cores_sao_opcionais():
    assert "\033[" not in pagina_comparacao(COMP, cores=False)
    assert "\033[" in pagina_comparacao(COMP, cores=True)
