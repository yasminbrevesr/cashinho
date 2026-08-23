"""As contas do contexto: variacao, volatilidade e correlacao."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.contexto import (
    MIN_AMOSTRA,
    NivelDeVolatilidade,
    classificar_volatilidade,
    correlacao_entre,
    correlacoes_relevantes,
    pearson,
    retornos_alinhados,
    variacao_do_dia,
    volatilidade_historica,
    volatilidade_por_candle,
)
from cashinho.models import Series

from .factories import ABERTURA, serie, serie_de_dias, serie_ruidosa


# --- variacao do dia --------------------------------------------------------


def test_variacao_compara_com_o_fechamento_do_pregao_anterior():
    s = serie_de_dias(dias=3, por_dia=4, base=100.0, passo=0.01)
    sessoes = s.sessions()
    esperado = (sessoes[-1][-1].close / sessoes[-2][-1].close - 1) * 100

    assert variacao_do_dia(s) == pytest.approx(esperado)


def test_com_um_pregao_so_usa_a_abertura_do_dia():
    s = serie([100.0, 102.0], timeframe="60m")

    assert variacao_do_dia(s) == pytest.approx(2.0)


def test_sem_dado_suficiente_a_variacao_e_desconhecida_e_nao_zero():
    """Zero diria 'mercado parado', que e' uma afirmacao que nao temos."""
    assert variacao_do_dia(Series("X", "60m", [])) is None
    assert variacao_do_dia(serie([100.0])) is None


# --- volatilidade -------------------------------------------------------------


def test_volatilidade_precisa_de_amostra():
    assert volatilidade_por_candle(serie([100.0] * 5)) is None


def test_serie_agitada_tem_volatilidade_maior_que_serie_calma():
    calma = serie_ruidosa(n=200, amplitude=0.001, semente=5)
    agitada = serie_ruidosa(n=200, amplitude=0.01, semente=5)

    assert volatilidade_por_candle(agitada) > volatilidade_por_candle(calma)


def test_a_referencia_e_o_proprio_historico_do_instrumento():
    s = serie_ruidosa(n=300, amplitude=0.004, semente=9)

    assert volatilidade_historica(s, janela=60) is not None


def test_historico_curto_nao_vira_referencia_inventada():
    assert volatilidade_historica(serie_ruidosa(n=80), janela=60) is None


def test_classificacao_da_volatilidade():
    assert classificar_volatilidade(1.0, 1.0) is NivelDeVolatilidade.NORMAL
    assert classificar_volatilidade(1.6, 1.0) is NivelDeVolatilidade.ALTA
    assert classificar_volatilidade(3.0, 1.0) is NivelDeVolatilidade.EXTREMA
    assert classificar_volatilidade(0.4, 1.0) is NivelDeVolatilidade.BAIXA


def test_sem_referencia_a_volatilidade_e_indisponivel():
    assert classificar_volatilidade(1.0, None) is NivelDeVolatilidade.INDISPONIVEL
    assert classificar_volatilidade(None, 1.0) is NivelDeVolatilidade.INDISPONIVEL
    assert classificar_volatilidade(1.0, 0.0) is NivelDeVolatilidade.INDISPONIVEL


# --- correlacao ------------------------------------------------------------------


def test_pearson_de_series_identicas_e_um():
    assert pearson([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)


def test_pearson_de_series_opostas_e_menos_um():
    assert pearson([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_serie_constante_nao_tem_correlacao_definida():
    assert pearson([1, 1, 1, 1], [1, 2, 3, 4]) is None


def test_pearson_precisa_de_dois_pontos():
    assert pearson([1], [1]) is None


def test_o_alinhamento_e_por_timestamp_e_nao_por_posicao():
    """Ibovespa e S&P 500 tem feriados diferentes: casar por posicao compara
    dias distintos e produz um numero falso."""
    a = serie([10.0, 11.0, 12.0, 13.0], symbol="A")
    # b comeca um candle depois: so tres timestamps coincidem
    b = serie([20.0, 21.0, 22.0, 23.0], symbol="B",
              inicio=ABERTURA + timedelta(minutes=60))

    ra, rb = retornos_alinhados(a, b)

    assert len(ra) == len(rb) == 2  # tres timestamps comuns -> dois retornos


def test_sem_timestamps_em_comum_nao_ha_correlacao():
    a = serie([10.0, 11.0, 12.0], symbol="A")
    b = serie([20.0, 21.0, 22.0], symbol="B",
              inicio=ABERTURA + timedelta(days=30))

    assert retornos_alinhados(a, b) == ([], [])


def test_correlacao_exige_amostra_minima():
    """Com 5 pontos qualquer par parece correlacionado."""
    a = serie([100.0 + i for i in range(6)], symbol="A")
    b = serie([200.0 + i * 2 for i in range(6)], symbol="B")

    assert correlacao_entre("A", a, "B", b) is None
    assert correlacao_entre("A", a, "B", b, min_amostra=3) is not None


def test_a_correlacao_carrega_a_amostra_junto():
    a = serie_ruidosa(n=100, semente=1, symbol="A")
    b = serie_ruidosa(n=100, semente=2, symbol="B")

    c = correlacao_entre("A", a, "B", b, min_amostra=10)

    assert c.amostra >= 10
    assert -1.0 <= c.valor <= 1.0


def test_so_entram_os_pares_acima_do_limiar():
    base = serie_ruidosa(n=120, semente=4, symbol="A")
    igual = Series("B", base.timeframe, list(base.candles))
    outro = serie_ruidosa(n=120, semente=77, symbol="C")

    achadas = correlacoes_relevantes(
        {"A": base, "B": igual, "C": outro}, limiar=0.99, min_amostra=30)

    pares = {(c.a, c.b) for c in achadas}
    assert ("A", "B") in pares
    assert ("A", "C") not in pares


def test_as_correlacoes_saem_da_mais_forte_para_a_mais_fraca():
    a = serie_ruidosa(n=150, semente=1, symbol="A")
    igual = Series("B", a.timeframe, list(a.candles))
    ruido = serie_ruidosa(n=150, semente=42, symbol="C")

    achadas = correlacoes_relevantes({"A": a, "B": igual, "C": ruido},
                                     limiar=0.0, min_amostra=30)
    valores = [abs(c.valor) for c in achadas]

    assert valores == sorted(valores, reverse=True)


def test_o_limiar_padrao_nao_e_zero():
    assert MIN_AMOSTRA >= 20
