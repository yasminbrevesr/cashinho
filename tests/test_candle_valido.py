"""O candle recusa estado impossivel.

O candle e' o atomo do sistema: ATR, estrutura, stop, tamanho de posicao e
preco de ordem saem dele. Sem estas travas, uma linha corrompida do feed
viraria tamanho de posicao la na frente, calada.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from cashinho.models import BRT, Candle, CandleInvalidoError

AGORA = datetime(2026, 8, 21, 10, 0, tzinfo=BRT)


def candle(o=30.0, h=30.5, l=29.5, c=30.2, v=1000.0) -> Candle:
    return Candle(AGORA, o, h, l, c, v)


# --- o que e' valido continua valido -------------------------------------


def test_candle_normal_e_aceito():
    assert candle().range == pytest.approx(1.0)


def test_candle_achatado_e_valido():
    """Um candle sem range acontece em ativo parado - nao e' erro."""
    assert Candle(AGORA, 30.0, 30.0, 30.0, 30.0, 0.0).range == 0.0


def test_volume_zero_e_valido():
    assert candle(v=0.0).volume == 0.0


def test_ruido_de_ponto_flutuante_nao_derruba_o_candle():
    """Um close 1e-12 acima da maxima veio de aritmetica, nao do mercado."""
    assert Candle(AGORA, 30.0, 30.5, 29.5, 30.5 + 1e-12, 100.0) is not None


# --- o que e' impossivel e recusado -----------------------------------------


def test_maxima_abaixo_da_minima_e_recusada():
    with pytest.raises(CandleInvalidoError, match="abaixo da minima"):
        candle(h=29.0, l=31.0)


def test_fechamento_fora_do_range_e_recusado():
    with pytest.raises(CandleInvalidoError, match="fora do range"):
        candle(c=35.0)


def test_abertura_fora_do_range_e_recusada():
    with pytest.raises(CandleInvalidoError, match="fora do range"):
        candle(o=25.0)


@pytest.mark.parametrize("campo", ["o", "h", "l", "c"])
def test_preco_zerado_ou_negativo_e_recusado(campo):
    with pytest.raises(CandleInvalidoError, match="maior que zero"):
        candle(**{campo: -1.0})


def test_volume_negativo_e_recusado():
    with pytest.raises(CandleInvalidoError, match="volume"):
        candle(v=-100.0)


def test_nan_e_recusado():
    with pytest.raises(CandleInvalidoError, match="nao e' um numero"):
        candle(c=float("nan"))


def test_infinito_e_recusado():
    with pytest.raises(CandleInvalidoError, match="nao e' um numero"):
        candle(h=float("inf"))


def test_o_erro_e_um_value_error():
    """Provedores ja capturam ValueError por linha: a linha ruim cai fora."""
    assert issubclass(CandleInvalidoError, ValueError)


# --- o provedor descarta a linha ruim em vez de quebrar a busca -----------------


def test_csv_descarta_linha_incoerente_e_mantem_o_resto(tmp_path):
    from cashinho.data.csv_provider import CSVProvider

    (tmp_path / "PETR4-5m.csv").write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-08-21 10:00:00,30.0,30.5,29.5,30.2,1000\n"
        "2026-08-21 10:05:00,30.2,29.0,31.0,30.4,1000\n"   # maxima < minima
        "2026-08-21 10:10:00,30.4,30.9,30.1,30.7,1000\n",
        encoding="utf-8")

    serie = CSVProvider(tmp_path).candles("PETR4", "5m", 5)

    assert len(serie) == 2
    assert all(c.high >= c.low for c in serie.candles)
