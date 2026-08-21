"""Alinhamento das camadas e navegacao no tempo."""

from __future__ import annotations

import pytest

from cashinho.core.mtf import (
    DadosInsuficientesError,
    LookaheadError,
    MTFConfig,
    MTFEngine,
    MTFError,
)
from cashinho.models import Series

from .factories import candle, serie_1m, serie_1m_sessao, serie_tf, ts

PADRAO = MTFConfig.padrao()


def _engine(n: int = 130) -> MTFEngine:
    return MTFEngine(PADRAO).alimentar(serie_1m(n=n))


def test_as_quatro_camadas_ficam_alinhadas_no_mesmo_instante():
    engine = _engine(n=130)  # 10:00 .. 12:09
    vista = engine.em(ts(12, 9))

    assert vista.camada("contexto").ts == ts(11, 0)  # 60m fechado as 12:00
    assert vista.camada("tendencia").ts == ts(11, 45)  # 15m fechado as 12:00
    assert vista.camada("setup").ts == ts(12, 0)  # 5m fechado as 12:05
    assert vista.camada("gatilho").ts == ts(12, 8)  # 1m fechado as 12:09


def test_snapshot_traz_none_para_camada_que_ainda_nao_fechou():
    vista = _engine(n=38).em(ts(10, 37))
    snap = vista.snapshot()

    assert snap["contexto"] is None  # 60m ainda em formacao
    assert snap["setup"].ts == ts(10, 30)
    assert list(snap) == ["contexto", "tendencia", "setup", "gatilho"]


def test_pronta_indica_quando_todas_as_camadas_tem_candle_fechado():
    engine = _engine(n=130)
    assert engine.em(ts(10, 37)).pronta() is False
    assert engine.em(ts(12, 9)).pronta() is True


def test_series_alimentam_os_indicadores_so_com_candles_fechados():
    vista = _engine(n=130).em(ts(12, 9))
    serie_15m = vista.serie_da_camada("tendencia")

    assert isinstance(serie_15m, Series)
    assert serie_15m.timeframe == "15m"
    assert len(serie_15m) == 8  # 10:00 .. 11:45
    assert serie_15m.last.ts == ts(11, 45)


def test_replay_nunca_entrega_candle_do_futuro():
    """Invariante do backtest: nada visivel pode fechar depois do instante."""
    engine = MTFEngine(PADRAO).alimentar(serie_1m_sessao(minutos=300))

    passos = 0
    for vista in engine.replay():
        passos += 1
        for tf in ("60m", "15m", "5m", "1m"):
            for bar in vista.barras_fechadas(tf):
                assert bar.fim <= vista.instante, f"{tf} vazou candle futuro"
    assert passos == 300


def test_replay_pode_ser_recortado_no_tempo():
    engine = _engine(n=130)
    vistas = list(engine.replay(desde=ts(11, 0), ate=ts(11, 10)))

    assert vistas[0].instante == ts(11, 0)
    assert vistas[-1].instante == ts(11, 10)


def test_agora_usa_o_fechamento_do_ultimo_candle_base():
    engine = _engine(n=38)  # ultimo 1m abre 10:37 e fecha 10:38
    assert engine.agora().instante == ts(10, 38)


def test_serie_injetada_tem_prioridade_sobre_o_resample():
    engine = _engine(n=130)
    engine.injetar(
        "60m",
        Series("PETR4", "60m", [candle(ts(10, 0), 1.0, 2.0, 0.5, 1.5, 999.0)]),
    )
    vista = engine.em(ts(12, 9))

    assert vista.ultimo("60m").close == 1.5
    assert len(vista.fechados("60m")) == 1


def test_timeframe_nao_configurado_e_reamostrado_sob_demanda():
    vista = _engine(n=130).em(ts(12, 9))
    serie_30m = vista.fechados("30m")

    assert len(serie_30m) == 4  # 10:00, 10:30, 11:00, 11:30
    assert serie_30m.last.ts == ts(11, 30)


def test_timeframe_que_nao_e_multiplo_da_base_e_recusado_na_consulta():
    config = MTFConfig(base="5m", camadas={"setup": "5m"})
    engine = MTFEngine(config).alimentar(serie_tf("5m", 20, 5))
    vista = engine.em(ts(11, 40))

    assert len(vista.fechados("15m")) == 6  # 15m e' multiplo de 5m: pode
    with pytest.raises(MTFError):
        vista.fechados("7m")  # 7m nao e': nao da para montar sem inventar dados


def test_serie_base_com_timeframe_errado_e_recusada():
    engine = MTFEngine(MTFConfig(base="5m", camadas={"gatilho": "5m"}))
    with pytest.raises(MTFError) as exc:
        engine.alimentar(serie_1m(n=10))
    assert "base" in str(exc.value)


def test_sem_dados_o_erro_e_de_dados_insuficientes_e_nao_de_lookahead():
    engine = MTFEngine(PADRAO).alimentar(Series("PETR4", "1m", []))
    vista = engine.em(ts(10, 37))

    with pytest.raises(DadosInsuficientesError):
        vista.ultimo("5m")


def test_consulta_antes_da_abertura_avisa_que_o_pregao_nao_comecou():
    engine = _engine(n=38)
    vista = engine.em(ts(9, 30))

    with pytest.raises(LookaheadError) as exc:
        vista.ultimo("5m")
    assert "10:00" in str(exc.value)


def test_combinacao_customizada_funciona_ponta_a_ponta():
    config = MTFConfig(base="1m", camadas={"macro": "1d", "diretor": "30m", "entrada": "3m"})
    engine = MTFEngine(config).alimentar(serie_1m_sessao(minutos=200))
    vista = engine.em(ts(13, 20))

    assert vista.camada("entrada").ts == ts(13, 15)
    assert vista.camada("diretor").ts == ts(12, 30)
    with pytest.raises(LookaheadError):
        vista.camada("macro")  # o diario so fecha as 17:55


def test_barra_fechada_no_tempo_mas_com_feed_incompleto_fica_marcada():
    """Feed que parou as 10:37 e consulta as 12:00: o 60m das 10:00 fechou no
    relogio, mas foi montado com 37 dos 60 minutos. Nao e' lookahead - e'
    dado velho -, entao ele aparece, porem marcado como parcial."""
    engine = _engine(n=38)  # 10:00 .. 10:37
    vista = engine.em(ts(12, 0))

    barra = vista.ultima_barra("60m")
    assert barra.inicio == ts(10, 0)
    assert barra.dados_parciais is True
    assert barra.n_base == 38


def test_em_formacao_some_quando_o_candle_fecha():
    engine = _engine(n=38)

    assert engine.em(ts(10, 37)).em_formacao("60m") is not None
    assert engine.em(ts(11, 0)).em_formacao("60m") is None
