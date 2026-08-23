"""A fita e o controle de velocidade."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from cashinho.core.mtf import LookaheadError
from cashinho.core.replay import FitaDeMercado, Relogio, Velocidade, dias_disponiveis, fita_do_dia

from .factories import ABERTURA, DIA, serie, serie_alta


# --- a fita ---------------------------------------------------------------------


def test_a_fita_comeca_antes_do_primeiro_candle():
    fita = FitaDeMercado(serie_alta(n=10))

    assert fita.posicao == -1
    assert fita.comecou is False
    assert len(fita) == 0
    assert fita.progresso == 0.0


def test_avancar_revela_um_candle_por_vez():
    dados = serie_alta(n=5)
    fita = FitaDeMercado(dados)

    for i in range(5):
        candle = fita.avancar()
        assert candle is dados.candles[i]
        assert fita.posicao == i
        assert len(fita) == i + 1


def test_a_fita_termina_e_avisa():
    fita = FitaDeMercado(serie_alta(n=3))
    for _ in range(3):
        fita.avancar()

    assert fita.terminou is True
    assert fita.progresso == pytest.approx(1.0)
    with pytest.raises(StopIteration):
        fita.avancar()


def test_indice_negativo_conta_de_tras_para_frente():
    fita = FitaDeMercado(serie_alta(n=10))
    for _ in range(5):
        fita.avancar()

    assert fita.candle(-1) is fita.atual
    assert fita.candle(-2).ts == fita.atual.ts - timedelta(minutes=1)


def test_serie_vazia_e_recusada():
    from cashinho.models import Series

    with pytest.raises(ValueError, match="sem candles"):
        FitaDeMercado(Series("PETR4", "1m", []))


# --- recorte por dia -------------------------------------------------------------


def test_fita_do_dia_recorta_o_pregao():
    dia1 = serie_alta(n=30)
    dia2 = serie_alta(n=20, inicio=ABERTURA + timedelta(days=1))
    from cashinho.models import Series

    dois = Series("PETR4", "1m", dia1.candles + dia2.candles)

    fita = fita_do_dia(dois, DIA)
    assert fita.total == 30
    assert all(c.ts.date() == DIA for c in fita._serie.candles)


def test_dia_sem_candles_e_recusado():
    with pytest.raises(ValueError, match="nenhum candle"):
        fita_do_dia(serie_alta(n=10), date(2027, 1, 1))


def test_dias_disponiveis_lista_os_pregoes():
    from cashinho.models import Series

    dois = Series("PETR4", "1m",
                  serie_alta(n=10).candles
                  + serie_alta(n=10, inicio=ABERTURA + timedelta(days=1)).candles)

    assert len(dias_disponiveis(dois)) == 2


def test_sem_dia_a_fita_pega_a_serie_inteira():
    assert fita_do_dia(serie_alta(n=40)).total == 40


# --- velocidade ---------------------------------------------------------------------


def test_as_velocidades_pedidas_existem():
    valores = {v.value for v in Velocidade}

    assert {"1x", "5x", "10x", "maxima"} <= valores


def test_o_multiplicador_de_cada_velocidade():
    assert Velocidade.X1.multiplicador == 1.0
    assert Velocidade.X5.multiplicador == 5.0
    assert Velocidade.X10.multiplicador == 10.0
    assert Velocidade.MAXIMA.instantanea is True


def test_o_intervalo_encolhe_com_a_velocidade():
    assert Relogio(Velocidade.X1).intervalo("5m") == pytest.approx(300.0)
    assert Relogio(Velocidade.X5).intervalo("5m") == pytest.approx(60.0)
    assert Relogio(Velocidade.X10).intervalo("5m") == pytest.approx(30.0)
    assert Relogio(Velocidade.MAXIMA).intervalo("5m") == 0.0


def test_o_intervalo_acompanha_o_timeframe():
    relogio = Relogio(Velocidade.X10)

    assert relogio.intervalo("1m") == pytest.approx(6.0)
    assert relogio.intervalo("15m") == pytest.approx(90.0)


def test_a_velocidade_maxima_nao_dorme():
    dormidas: list[float] = []
    relogio = Relogio(Velocidade.MAXIMA, dormir=dormidas.append)

    relogio.esperar("5m")
    assert dormidas == []


def test_a_velocidade_lenta_dorme_o_previsto():
    dormidas: list[float] = []
    relogio = Relogio(Velocidade.X10, dormir=dormidas.append)

    relogio.esperar("1m")
    assert dormidas == [pytest.approx(6.0)]


@pytest.mark.parametrize("texto,esperado", [
    ("1x", Velocidade.X1), ("5X", Velocidade.X5), ("10x", Velocidade.X10),
    ("maxima", Velocidade.MAXIMA), ("max", Velocidade.MAXIMA), (" 60x ", Velocidade.X60),
])
def test_a_velocidade_e_lida_de_texto(texto, esperado):
    assert Velocidade.de_texto(texto) is esperado


def test_velocidade_invalida_e_recusada():
    with pytest.raises(ValueError, match="velocidade invalida"):
        Velocidade.de_texto("turbo")
