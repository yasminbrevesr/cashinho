"""Indicadores de volume - inclusive os que ainda nao tem consumidor."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.indicators.volume import (
    fluxo_direcional,
    perfil_volume,
    volume_relativo,
    vwap_sessao,
)
from cashinho.models import BRT, Candle

BASE = datetime(2026, 8, 21, 10, 0, tzinfo=BRT)


def candles(valores, volume=1000.0):
    return [Candle(BASE + timedelta(minutes=5 * i), v, v, v, v, volume)
            for i, v in enumerate(valores)]


def test_perfil_com_candle_parado_na_maxima_da_serie():
    """O candle no topo caia um balde alem do fim e zerava o divisor."""
    perfil = perfil_volume(candles([30.0, 30.5]))

    assert perfil is not None
    assert perfil.poc > 0


def test_perfil_com_candle_parado_na_minima():
    assert perfil_volume(candles([30.5, 30.0])) is not None


def test_perfil_sem_range_nao_e_calculado():
    assert perfil_volume(candles([30.0, 30.0])) is None


def test_perfil_sem_candles_e_none():
    assert perfil_volume([]) is None


def test_o_poc_fica_dentro_do_range():
    cs = candles([30.0, 30.4, 30.2, 30.9, 30.1])
    perfil = perfil_volume(cs)

    assert min(c.low for c in cs) <= perfil.poc <= max(c.high for c in cs)


def test_volume_relativo_inclui_o_proprio_candle_na_media():
    """Convencao da casa, registrada aqui: a janela da media inclui o candle
    que esta sendo medido, entao um pico de 3x le 2,7x. Quem ajustar o
    limiar de volume do score precisa saber disso."""
    volumes = [1000.0] * 20 + [3000.0]

    media = (1000.0 * 19 + 3000.0) / 20
    assert volume_relativo(volumes, period=20)[-1] == pytest.approx(3000.0 / media)


def test_volume_relativo_sem_media_ainda_e_none():
    assert volume_relativo([1000.0, 1000.0], period=20)[-1] is None


def test_vwap_da_sessao_fica_dentro_do_range_do_dia():
    cs = candles([30.0, 30.4, 30.2, 30.9])
    v = vwap_sessao(cs).vwap[-1]

    assert min(c.low for c in cs) <= v <= max(c.high for c in cs)


def test_as_bandas_da_vwap_cercam_a_vwap():
    v = vwap_sessao(candles([30.0, 30.4, 30.2, 30.9, 30.5]))
    i = -1

    assert v.banda_inf1[i] <= v.vwap[i] <= v.banda_sup1[i]
    assert v.banda_inf2[i] <= v.banda_inf1[i]
    assert v.banda_sup2[i] >= v.banda_sup1[i]


def test_fluxo_direcional_entre_zero_e_um():
    f = fluxo_direcional(candles([30.0, 30.4, 30.2, 30.9]))

    assert f is None or 0.0 <= f <= 1.0
