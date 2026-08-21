"""Regra critica do motor multi-timeframe: nada de olhar para o futuro.

Um timeframe superior so pode ser consultado depois que o candle dele fechou.
Se a decisao acontece no 1m as 10:37, o candle de 60m das 10:00 (que so fecha
as 11:00) ainda nao existe do ponto de vista do robo - consultar esse candle
e' vazamento de informacao futura e deve levantar ``LookaheadError``.
"""

from __future__ import annotations

import pytest

from cashinho.core.mtf import LookaheadError, MTFConfig, MTFEngine
from cashinho.models import Series

from .factories import candle, serie_1m, ts

CONFIG = MTFConfig(
    base="1m",
    camadas={"contexto": "60m", "tendencia": "15m", "setup": "5m", "gatilho": "1m"},
)


def _engine_com_60m_em_formacao() -> MTFEngine:
    """1m ate 10:37 e um candle de 60m das 10:00 (fecha as 11:00) injetado."""
    engine = MTFEngine(CONFIG)
    engine.alimentar(serie_1m(n=38))  # 10:00 .. 10:37
    engine.injetar(
        "60m",
        Series("PETR4", "60m", [candle(ts(10, 0), 30.0, 30.9, 29.8, 30.4, 500_000.0)]),
    )
    return engine


def test_consultar_60m_em_formacao_a_partir_do_1m_levanta_lookahead():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 37))

    with pytest.raises(LookaheadError):
        vista.ultimo("60m")


def test_erro_de_lookahead_explica_quando_o_candle_fecha():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 37))

    with pytest.raises(LookaheadError) as exc:
        vista.ultimo("60m")

    msg = str(exc.value)
    assert "60m" in msg
    assert "11:00" in msg  # o instante em que o candle passa a ser consultavel


def test_consulta_por_papel_tambem_e_bloqueada():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 37))

    with pytest.raises(LookaheadError):
        vista.camada("contexto")


def test_candle_em_formacao_nao_aparece_entre_os_fechados():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 37))

    assert len(vista.fechados("60m")) == 0


def test_candle_em_formacao_so_e_acessivel_de_forma_explicita():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 37))

    em_formacao = vista.em_formacao("60m")
    assert em_formacao is not None
    assert em_formacao.inicio == ts(10, 0)
    assert em_formacao.fim == ts(11, 0)
    assert em_formacao.fechada_em(ts(10, 37)) is False


def test_apos_o_fechamento_o_candle_de_60m_fica_disponivel():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(11, 0))

    ultimo = vista.ultimo("60m")
    assert ultimo.ts == ts(10, 0)
    assert len(vista.fechados("60m")) == 1


def test_um_segundo_antes_do_fechamento_ainda_e_lookahead():
    engine = _engine_com_60m_em_formacao()
    vista = engine.em(ts(10, 59, 59))

    with pytest.raises(LookaheadError):
        vista.ultimo("60m")


def test_serie_reamostrada_nao_vaza_o_candle_em_formacao():
    """Sem injecao: o 60m sai do resample do 1m e mesmo assim nao vaza."""
    engine = MTFEngine(CONFIG)
    engine.alimentar(serie_1m(n=38))  # 10:00 .. 10:37
    vista = engine.em(ts(10, 37))

    assert len(vista.fechados("60m")) == 0
    with pytest.raises(LookaheadError):
        vista.ultimo("60m")

    # o 5m das 10:35 ainda esta em formacao as 10:37,
    # mas o das 10:30 (10:30-10:35) ja fechou e pode ser consultado
    assert vista.ultimo("5m").ts == ts(10, 30)
    assert vista.fechados("5m").last.ts == ts(10, 30)


def test_timeframe_de_gatilho_usa_o_candle_recem_fechado():
    engine = MTFEngine(CONFIG)
    engine.alimentar(serie_1m(n=38))  # ultimo candle de 1m abre 10:37 e fecha 10:38
    vista = engine.em(ts(10, 38))

    assert vista.ultimo("1m").ts == ts(10, 37)
    assert vista.camada("gatilho").ts == ts(10, 37)
