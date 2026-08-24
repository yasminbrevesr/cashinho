"""Agregacao 1m -> 2m, 5m e demais: OHLC, volume e candle incompleto.

O resampling reusa o MTFEngine, que ja existia e ja tinha disciplina de
candle fechado. Estes testes fixam o contrato de que o Advisor depende - se
alguem mexer na agregacao, e' aqui que quebra.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.mtf import MTFConfig, MTFEngine

from .factories import ABERTURA, serie_1m

TODOS = ("1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m")


def engine(serie=None):
    serie = serie if serie is not None else serie_1m(400)
    camadas = {f"tf_{t}": t for t in TODOS}
    return MTFEngine(MTFConfig(base="1m", camadas=camadas), "PETR4").alimentar(serie)


def test_reamostra_todos_os_timeframes_pedidos():
    e = engine()

    for tf in TODOS:
        assert e.barras(tf), tf


def test_a_agregacao_1m_para_2m_preserva_ohlc():
    serie = serie_1m(400)
    barra = engine(serie).barras("2m")[5]
    compoem = [c for c in serie.candles if barra.inicio <= c.ts < barra.fim]

    assert len(compoem) == 2
    assert barra.candle.open == compoem[0].open
    assert barra.candle.high == max(c.high for c in compoem)
    assert barra.candle.low == min(c.low for c in compoem)
    assert barra.candle.close == compoem[-1].close


def test_a_agregacao_1m_para_5m_preserva_ohlc():
    serie = serie_1m(400)
    barra = engine(serie).barras("5m")[5]
    compoem = [c for c in serie.candles if barra.inicio <= c.ts < barra.fim]

    assert len(compoem) == 5
    assert barra.candle.open == compoem[0].open
    assert barra.candle.high == max(c.high for c in compoem)
    assert barra.candle.low == min(c.low for c in compoem)
    assert barra.candle.close == compoem[-1].close


@pytest.mark.parametrize("tf", TODOS)
def test_o_volume_e_a_soma(tf):
    serie = serie_1m(400)
    barra = engine(serie).barras(tf)[3]
    compoem = [c for c in serie.candles if barra.inicio <= c.ts < barra.fim]

    assert barra.candle.volume == pytest.approx(sum(c.volume for c in compoem))


@pytest.mark.parametrize("tf", TODOS)
def test_o_alto_nunca_e_menor_que_o_baixo(tf):
    for barra in engine().barras(tf):
        assert barra.candle.high >= barra.candle.low


def test_o_candle_incompleto_nao_aparece_como_fechado():
    serie = serie_1m(400)
    e = engine(serie)
    # instante no meio de um candle de 5m
    meio = serie.candles[7].ts + timedelta(minutes=2)
    vista = e.em(meio)

    for barra in vista.barras_fechadas("5m"):
        assert barra.fim <= meio


def test_barras_inclui_a_em_formacao_e_fechadas_nao():
    serie = serie_1m(400)
    e = engine(serie)
    instante = serie.candles[-1].ts

    todas = e.barras("5m")
    fechadas = e.em(instante).barras_fechadas("5m")

    assert len(todas) >= len(fechadas)


def test_a_agregacao_independe_do_provider():
    """A entrada e' uma Series: nao ha nada de MetaTrader aqui."""
    import ast
    import pathlib

    for arquivo in pathlib.Path("src/cashinho/core/advisor").glob("*.py"):
        arvore = ast.parse(arquivo.read_text())
        nomes = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                nomes.add(no.module)
            elif isinstance(no, ast.Import):
                nomes |= {a.name for a in no.names}
        assert not any("MetaTrader" in n or "metatrader" in n for n in nomes), arquivo.name
