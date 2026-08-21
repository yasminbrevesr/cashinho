"""Resample ancorado na sessao da B3."""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from cashinho.core.mtf import (
    SESSAO_B3,
    ConfiguracaoInvalidaError,
    Sessao,
    janela,
    parse_timeframe,
    reamostrar,
)
from cashinho.models import Series

from .factories import candle, concatena, serie_1m, serie_1m_sessao, ts


def test_janela_de_60m_comeca_na_abertura_do_pregao_e_nao_na_hora_cheia():
    inicio, fim = janela(ts(10, 37), parse_timeframe("60m"))
    assert (inicio, fim) == (ts(10, 0), ts(11, 0))


def test_janela_de_15m_ancorada_na_abertura():
    assert janela(ts(10, 44), parse_timeframe("15m")) == (ts(10, 30), ts(10, 45))
    assert janela(ts(10, 45), parse_timeframe("15m")) == (ts(10, 45), ts(11, 0))


def test_ultimo_candle_do_dia_e_truncado_no_fechamento():
    """As 17:00 comeca um balde de 60m que nao chega as 18:00: fecha as 17:55."""
    inicio, fim = janela(ts(17, 30), parse_timeframe("60m"))
    assert inicio == ts(17, 0)
    assert fim == ts(17, 55)  # fim da sessao, nao 18:00


def test_candle_fora_do_pregao_nao_tem_janela():
    assert janela(ts(9, 30), parse_timeframe("5m")) is None  # pre-abertura
    assert janela(ts(18, 30), parse_timeframe("5m")) is None  # after-market


def test_fim_de_semana_nao_tem_sessao():
    sabado = ts(12, 0, dia=22)  # 22/08/2026 e' sabado
    assert janela(sabado, parse_timeframe("5m")) is None


def test_resample_de_1m_para_5m_agrega_ohlcv_corretamente():
    serie = serie_1m(n=10)  # 10:00 .. 10:09
    bars = reamostrar(serie, "5m", base="1m")

    assert len(bars) == 2
    primeira = bars[0]
    assert primeira.inicio == ts(10, 0)
    assert primeira.fim == ts(10, 5)
    assert primeira.n_base == 5
    assert primeira.candle.open == serie.candles[0].open
    assert primeira.candle.close == serie.candles[4].close
    assert primeira.candle.high == max(c.high for c in serie.candles[:5])
    assert primeira.candle.low == min(c.low for c in serie.candles[:5])
    assert primeira.candle.volume == pytest.approx(sum(c.volume for c in serie.candles[:5]))


def test_barra_incompleta_e_marcada_como_parcial():
    serie = serie_1m(n=8)  # 10:00 .. 10:07: o segundo balde de 5m tem so 3 candles
    bars = reamostrar(serie, "5m", base="1m")

    assert bars[0].dados_parciais is False
    assert bars[-1].dados_parciais is True
    assert bars[-1].n_base == 3


def test_resample_nao_mistura_dias_diferentes():
    dois_dias = concatena(serie_1m_sessao(dia=20, minutos=60), serie_1m_sessao(dia=21, minutos=60))
    bars = reamostrar(dois_dias, "60m", base="1m")

    assert [b.inicio for b in bars] == [ts(10, 0, dia=20), ts(10, 0, dia=21)]
    assert all(b.inicio.date() == b.fim.date() for b in bars)


def test_resample_descarta_candles_fora_do_pregao():
    dentro = serie_1m(n=5)
    fora = Series(
        "PETR4",
        "1m",
        [candle(ts(9, 55), 30.0, 30.1, 29.9, 30.0), candle(ts(18, 10), 31.0, 31.1, 30.9, 31.0)],
    )
    serie = concatena(dentro, fora)
    bars = reamostrar(serie, "5m", base="1m")

    assert len(bars) == 1
    assert bars[0].n_base == 5


def test_timeframe_diario_cobre_a_sessao_inteira():
    serie = serie_1m_sessao(minutos=475)  # 10:00 .. 17:54
    bars = reamostrar(serie, "1d", base="1m")

    assert len(bars) == 1
    assert bars[0].inicio == ts(10, 0)
    assert bars[0].fim == ts(17, 55)
    assert bars[0].n_base == 475


def test_resample_para_timeframe_que_nao_e_multiplo_da_base_e_recusado():
    with pytest.raises(ConfiguracaoInvalidaError):
        reamostrar(serie_1m(n=10), "7m", base="5m")


def test_sessao_customizada_muda_a_ancoragem():
    """Mini indice abre as 9:00: o balde de 60m das 9:00 termina as 10:00."""
    sessao_win = Sessao(abertura=time(9, 0), fechamento=time(18, 25))
    inicio, fim = janela(ts(9, 30), parse_timeframe("60m"), sessao_win)
    assert (inicio, fim) == (ts(9, 0), ts(10, 0))


def test_rotulagem_por_fechamento_e_suportada():
    """Feeds que carimbam a barra no fechamento nao podem deslocar a janela."""
    serie = Series("PETR4", "5m", [candle(ts(10, 5), 30.0, 30.3, 29.9, 30.2)])
    bars = reamostrar(serie, "5m", base="5m", rotulagem="fechamento")

    assert bars[0].inicio == ts(10, 0)
    assert bars[0].fim == ts(10, 5)
