"""O validador de qualidade: dado invalido bloqueia a analise."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.data.qualidade import (
    ConfigQualidade,
    Gravidade,
    ValidadorDeQualidade,
)
from cashinho.models import BRT, Candle, Series

from .factories import AGORA, serie


def validador(**campos):
    return ValidadorDeQualidade(ConfigQualidade(**campos), relogio=lambda: AGORA)


def com_candles(candles, timeframe="5m"):
    return Series("PETR4", timeframe, list(candles))


def candle(minuto: int, o=30.0, h=30.5, l=29.5, c=30.2, v=1000.0):
    return Candle(AGORA - timedelta(minutes=minuto), o, h, l, c, v)


# --- serie boa -----------------------------------------------------------


def test_serie_saudavel_passa():
    q = validador().validar(serie(n=20, timeframe="1d"))

    assert q.valida is True
    assert q.rotulo == "OK"


def test_serie_vazia_bloqueia():
    q = validador().validar(Series("PETR4", "5m", []))

    assert q.valida is False
    assert q.bloqueios[0].chave == "serie_vazia"


# --- problemas que so aparecem no conjunto ----------------------------------


def test_timestamp_duplicado_bloqueia():
    """O mesmo instante duas vezes vira volume e retorno inflados."""
    c1 = candle(10)
    q = validador().validar(com_candles([c1, c1]))

    assert q.valida is False
    assert any(p.chave == "timestamp_duplicado" for p in q.bloqueios)


def test_fora_de_ordem_bloqueia():
    q = validador().validar(com_candles([candle(5), candle(30)]))

    assert q.valida is False
    assert any(p.chave == "fora_de_ordem" for p in q.bloqueios)


def test_timestamp_futuro_bloqueia():
    futuro = Candle(AGORA + timedelta(hours=2), 30, 30.5, 29.5, 30.2, 1000)
    q = validador().validar(com_candles([candle(10), futuro]))

    assert q.valida is False
    assert any(p.chave == "timestamp_futuro" for p in q.bloqueios)


def test_pequena_folga_de_relogio_nao_e_futuro():
    """Relogios nao batem ao segundo; 30s de folga nao e' look-ahead."""
    quase = Candle(AGORA + timedelta(seconds=30), 30, 30.5, 29.5, 30.2, 1000)
    q = validador(folga_futuro_s=60).validar(com_candles([candle(10), quase]))

    assert not any(p.chave == "timestamp_futuro" for p in q.problemas)


def test_timestamp_sem_fuso_bloqueia():
    ingenuo = Candle.__new__(Candle)
    object.__setattr__(ingenuo, "ts", datetime(2026, 8, 21, 10, 0))
    for campo, valor in (("open", 30.0), ("high", 30.5), ("low", 29.5),
                         ("close", 30.2), ("volume", 1000.0)):
        object.__setattr__(ingenuo, campo, valor)

    q = validador().validar(com_candles([ingenuo]))

    assert q.valida is False
    assert q.bloqueios[0].chave == "timestamp_sem_fuso"


def test_ohlc_incoerente_bloqueia():
    """Rede de seguranca: o Candle ja barra, mas serie montada a mao nao passa."""
    ruim = Candle.__new__(Candle)
    for campo, valor in (("ts", AGORA - timedelta(minutes=5)), ("open", 30.0),
                         ("high", 29.0), ("low", 31.0), ("close", 30.0),
                         ("volume", 1000.0)):
        object.__setattr__(ruim, campo, valor)

    q = validador().validar(com_candles([ruim]))

    assert q.valida is False
    assert any(p.chave == "ohlc_incoerente" for p in q.bloqueios)


def test_volume_negativo_bloqueia():
    ruim = Candle.__new__(Candle)
    for campo, valor in (("ts", AGORA - timedelta(minutes=5)), ("open", 30.0),
                         ("high", 30.5), ("low", 29.5), ("close", 30.0),
                         ("volume", -5.0)):
        object.__setattr__(ruim, campo, valor)

    assert validador().validar(com_candles([ruim])).valida is False


# --- avisos (nao bloqueiam) --------------------------------------------------


def test_serie_antiga_avisa_sem_bloquear():
    antiga = serie(n=10, timeframe="1d",
                   inicio=AGORA - timedelta(days=400), passo_min=60 * 24)
    q = validador(idade_maxima_dias=30).validar(antiga)

    assert q.valida is True
    assert any(p.chave == "serie_antiga" for p in q.avisos)


def test_buraco_dentro_do_pregao_avisa():
    # ja em ordem cronologica: 60 min atras, 55 min atras, 5 min atras.
    # O salto de 50 min vale 10 candles de 5m, acima do tolerado
    candles = [candle(60), candle(55), candle(5)]
    q = validador().validar(com_candles(candles, "5m"))

    assert any(p.chave == "gap_inesperado" for p in q.avisos)


def test_virada_de_dia_nao_e_buraco():
    """Entre pregoes o buraco e' a noite, nao defeito."""
    dia1 = [Candle(datetime(2026, 8, 20, 17, 50, tzinfo=BRT), 30, 30.5, 29.5, 30.2, 1e3)]
    dia2 = [Candle(datetime(2026, 8, 21, 10, 0, tzinfo=BRT), 30, 30.5, 29.5, 30.2, 1e3)]
    q = validador().validar(com_candles(dia1 + dia2, "5m"))

    assert not any(p.chave == "gap_inesperado" for p in q.problemas)


def test_o_veredito_serializa():
    import json

    json.dumps(validador().validar(serie(n=5, timeframe="1d")).para_dict())
