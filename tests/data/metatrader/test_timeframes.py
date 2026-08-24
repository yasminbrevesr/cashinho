"""Os seis timeframes, conferidos campo a campo.

Sem terminal real aqui, o dublê devolve o mesmo formato que a maquina de
verdade devolveu. O que estes testes provam e' o **tratamento**: mapeamento,
OHLC coerente, volume, fuso e o corte do candle em formacao.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.data.base import DataError
from cashinho.data.metatrader import TIMEFRAMES
from cashinho.models import BRT

from .factories import AGORA, MT5Falso, candle, provedor

# minutos que cada timeframe ocupa - para montar candles fechados de verdade
DURACAO = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1d": 375}


def serie_de(timeframe: str, quantos: int = 4, com_aberto: bool = False):
    """Candles fechados (e, se pedido, um em formacao) para o timeframe."""
    passo = DURACAO[timeframe]
    fechados = [candle(passo * (i + 1)) for i in range(quantos)][::-1]
    linhas = list(fechados)
    if com_aberto:
        linhas.append(candle(0))     # abriu agora: ainda nao fechou
    return provedor(MT5Falso(candles=linhas)).candles("PETR4", timeframe, 5)


# --- mapeamento -----------------------------------------------------------


def test_os_seis_timeframes_pedidos_estao_mapeados():
    assert set(TIMEFRAMES) == {"1m", "5m", "15m", "30m", "60m", "1d"}


def test_o_mapeamento_aponta_para_as_constantes_do_mt5():
    assert TIMEFRAMES["1m"] == "TIMEFRAME_M1"
    assert TIMEFRAMES["5m"] == "TIMEFRAME_M5"
    assert TIMEFRAMES["15m"] == "TIMEFRAME_M15"
    assert TIMEFRAMES["30m"] == "TIMEFRAME_M30"
    assert TIMEFRAMES["60m"] == "TIMEFRAME_H1"
    assert TIMEFRAMES["1d"] == "TIMEFRAME_D1"


def test_cada_timeframe_usa_a_constante_certa():
    from .factories import terminal
    from cashinho.data.metatrader import MetaTraderMarketDataProvider

    esperado = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 16385, "1d": 16408}
    for tf, constante in esperado.items():
        mt5 = MT5Falso(candles=[candle(DURACAO[tf] * (i + 1)) for i in (3, 2, 1)])
        p = MetaTraderMarketDataProvider(terminal=terminal(mt5), relogio=lambda: AGORA)
        p.conectar()
        p.candles("PETR4", tf, 5)
        assert any(f", {constante})" in c for c in mt5.chamadas), tf


# --- campos preservados ------------------------------------------------------------


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_o_ohlc_chega_coerente(timeframe):
    for c in serie_de(timeframe).candles:
        assert c.high >= c.open and c.high >= c.close and c.high >= c.low
        assert c.low <= c.open and c.low <= c.close


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_o_volume_real_e_preferido_ao_tick_volume(timeframe):
    # o dublê traz tick_volume=1200 e real_volume=340000
    assert all(c.volume == 340_000 for c in serie_de(timeframe).candles)


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_todo_timestamp_tem_fuso(timeframe):
    assert all(c.ts.tzinfo is not None for c in serie_de(timeframe).candles)


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_o_horario_e_o_do_servidor_sem_deslocamento(timeframe):
    """O dublê marca o candle no relogio de Sao Paulo; ele chega igual."""
    serie = serie_de(timeframe)
    esperado = AGORA - timedelta(minutes=DURACAO[timeframe])

    assert serie.candles[-1].ts.hour == esperado.hour


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_os_candles_saem_em_ordem(timeframe):
    ts = [c.ts for c in serie_de(timeframe).candles]

    assert ts == sorted(ts)


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_o_symbol_e_o_timeframe_vao_na_serie(timeframe):
    serie = serie_de(timeframe)

    assert serie.symbol == "PETR4"
    assert serie.timeframe == timeframe


# --- candle aberto x fechado -----------------------------------------------------------


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_o_candle_em_formacao_nao_entra(timeframe):
    com_aberto = serie_de(timeframe, quantos=3, com_aberto=True)
    so_fechados = serie_de(timeframe, quantos=3, com_aberto=False)

    assert len(com_aberto) == len(so_fechados) == 3


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_todo_candle_entregue_ja_fechou(timeframe):
    duracao = timedelta(minutes=DURACAO[timeframe])

    for c in serie_de(timeframe, com_aberto=True).candles:
        assert c.ts + duracao <= AGORA


def test_um_candle_de_60m_aberto_ha_59_minutos_ainda_nao_fechou():
    """O corte e' pela duracao do periodo, nao pela posicao na lista."""
    p = provedor(MT5Falso(candles=[candle(120), candle(59)]))

    serie = p.candles("PETR4", "60m", 5)

    assert len(serie) == 1
    assert serie.candles[0].ts == AGORA.replace(microsecond=0) - timedelta(minutes=120)


def test_so_candle_em_formacao_vira_erro_explicado():
    p = provedor(MT5Falso(candles=[candle(0)]))

    with pytest.raises(DataError, match="em formacao"):
        p.candles("PETR4", "1m", 1)
