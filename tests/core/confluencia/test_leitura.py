"""Os leitores de cada camada, isolados."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.confluencia import (
    ContextState,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
    ler_context,
    ler_setup,
    ler_trend,
    ler_trigger,
)
from cashinho.models import Series

from .factories import ABERTURA, serie_1m, serie_alta, serie_baixa, serie_parada

QUANDO = ABERTURA + timedelta(hours=5)


def _ler(leitor, serie):
    return leitor(serie, QUANDO, QUANDO)


# --- context ------------------------------------------------------------------


def test_contexto_de_alta():
    c = _ler(ler_context, serie_alta())

    assert c.estado is ContextState.BULLISH
    assert c.vies is Vies.BULLISH
    assert c.bullish
    assert c.forca > 0
    assert "empilhadas para alta" in c.razoes[0]


def test_contexto_de_baixa():
    c = _ler(ler_context, serie_baixa())

    assert c.estado is ContextState.BEARISH
    assert c.bearish


def test_contexto_neutro_quando_as_medias_se_embaralham():
    c = _ler(ler_context, serie_parada())

    assert c.estado is ContextState.NEUTRAL
    assert c.vies is Vies.NEUTRAL


def test_serie_curta_nao_inventa_contexto():
    c = _ler(ler_context, serie_alta(n=20))

    assert c.estado is ContextState.NEUTRAL
    assert "candles fechados" in c.razoes[0]


# --- trend ----------------------------------------------------------------------


def test_tendencia_usa_sideways_no_lugar_de_neutral():
    assert _ler(ler_trend, serie_alta()).estado is TrendState.BULLISH
    assert _ler(ler_trend, serie_baixa()).estado is TrendState.BEARISH
    assert _ler(ler_trend, serie_parada()).estado is TrendState.SIDEWAYS


def test_papel_e_fixado_pela_classe():
    assert _ler(ler_context, serie_alta()).papel == "context"
    assert _ler(ler_trend, serie_alta()).papel == "trend"
    assert _ler(ler_setup, serie_alta()).papel == "setup"
    assert _ler(ler_trigger, serie_alta()).papel == "trigger"


# --- setup ------------------------------------------------------------------------


def test_setup_reconhece_pullback_em_tendencia():
    """Alta consistente e depois uma correcao: o setup vira pullback."""
    closes = [30.0 * 1.002 ** i for i in range(70)]
    for _ in range(6):
        closes.append(closes[-1] * 0.997)
    s = _ler(ler_setup, serie_1m(closes))

    assert s.estado in (SetupState.PULLBACK, SetupState.BREAKOUT, SetupState.NONE)
    if s.estado is SetupState.PULLBACK:
        assert s.detalhes["vies"] == Vies.BULLISH.value
        assert s.existe


def test_setup_sem_formacao_e_none():
    s = _ler(ler_setup, serie_parada())

    assert s.estado is SetupState.NONE
    assert s.existe is False


def test_setup_guarda_niveis_para_o_engine_usar():
    s = _ler(ler_setup, serie_alta())

    assert "atr" in s.detalhes and s.detalhes["atr"] > 0
    assert "preco" in s.detalhes
    assert "regime" in s.detalhes


def test_setup_com_poucos_candles_nao_quebra():
    s = _ler(ler_setup, serie_alta(n=4))

    assert s.estado is SetupState.NONE
    assert "candles fechados" in s.razoes[0]


# --- trigger ---------------------------------------------------------------------


def test_gatilho_de_rompimento_exige_volume():
    closes = [30.0] * 20 + [30.5]
    com_volume = serie_1m(closes, volumes=[10_000.0] * 20 + [40_000.0])
    sem_volume = serie_1m(closes, volumes=[10_000.0] * 21)

    assert _ler(ler_trigger, com_volume).estado is TriggerState.BREAKOUT_WITH_VOLUME
    assert _ler(ler_trigger, sem_volume).estado is not TriggerState.BREAKOUT_WITH_VOLUME


def test_gatilho_de_rompimento_guarda_a_direcao():
    alta = serie_1m([30.0] * 20 + [30.5], volumes=[10_000.0] * 20 + [40_000.0])
    baixa = serie_1m([30.0] * 20 + [29.5], volumes=[10_000.0] * 20 + [40_000.0])

    assert _ler(ler_trigger, alta).detalhes["vies"] == Vies.BULLISH.value
    assert _ler(ler_trigger, baixa).detalhes["vies"] == Vies.BEARISH.value


def test_gatilho_de_retomada_de_media():
    """Queda que perde a media e um candle que a recupera."""
    closes = [30.0 * (1 - 0.001) ** i for i in range(30)]
    closes.append(closes[-1] * 1.006)
    t = _ler(ler_trigger, serie_1m(closes))

    assert t.estado in (TriggerState.MA_RECLAIM, TriggerState.BREAKOUT_WITH_VOLUME,
                        TriggerState.REJECTION_WICK)


def test_sem_gatilho_o_estado_e_none():
    t = _ler(ler_trigger, serie_parada())

    assert t.estado is TriggerState.NONE
    assert t.disparou is False
    assert "nenhum gatilho" in t.razoes[0]


def test_gatilho_registra_o_volume_relativo():
    t = _ler(ler_trigger, serie_1m([30.0] * 20 + [30.5], volumes=[10_000.0] * 20 + [40_000.0]))

    assert t.detalhes["volume_relativo"] > 1.0


# --- isolamento entre camadas -------------------------------------------------------


def test_cada_leitor_recebe_apenas_a_serie_do_seu_timeframe():
    """Nenhum leitor tem como olhar outra camada - ele so recebe uma serie."""
    import inspect

    for leitor in (ler_context, ler_trend, ler_setup, ler_trigger):
        parametros = list(inspect.signature(leitor).parameters)
        assert parametros[:3] == ["serie", "fechado_em", "lido_em"]
        assert "leitura" not in parametros and "vista" not in parametros
