"""Montagem do painel de indicadores."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cashinho.domain.enums import Timeframe
from cashinho.pipeline.indicators import IndicatorSelection, compute_panel
from tests.unit.test_indicators import series_from_closes

BASE = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


def _serie(count: int = 80, timeframe: Timeframe = Timeframe.M5):
    return series_from_closes(
        [10 + (i % 11) * 0.3 for i in range(count)], timeframe=timeframe
    )


def test_selecao_vazia_nao_calcula_nada() -> None:
    panel = compute_panel(_serie(), IndicatorSelection())
    assert not panel.has_content
    assert not panel.failures


def test_selecao_vazia_e_detectada() -> None:
    assert not IndicatorSelection().any_selected
    assert IndicatorSelection(rsi_period=14).any_selected


def test_overlays_e_osciladores_ficam_separados() -> None:
    """Separacao existe porque as escalas sao incompativeis no grafico."""
    panel = compute_panel(
        _serie(),
        IndicatorSelection(
            sma_periods=(20,), ema_periods=(9,), vwap=True,
            rsi_period=14, macd=True, atr_period=14,
        ),
    )
    assert set(panel.overlays) == {"SMA(20)", "EMA(9)", "VWAP"}
    assert set(panel.oscillators) == {"RSI(14)", "MACD", "ATR(14)"}


def test_multiplos_periodos_geram_entradas_distintas() -> None:
    panel = compute_panel(_serie(), IndicatorSelection(sma_periods=(9, 20, 50)))
    assert set(panel.overlays) == {"SMA(9)", "SMA(20)", "SMA(50)"}


def test_falha_de_um_indicador_nao_derruba_os_demais() -> None:
    """Com 30 candles a EMA(9) e valida; o MACD(12,26,9) nao."""
    panel = compute_panel(
        _serie(count=30),
        IndicatorSelection(ema_periods=(9,), macd=True),
    )
    assert "EMA(9)" in panel.overlays
    assert "MACD" in panel.failures
    assert "ao menos 35" in panel.failures["MACD"]


def test_falha_registra_o_motivo() -> None:
    """Indicador ausente por falta de dados e indicador nao pedido exigem
    reacoes diferentes; sem o motivo, os dois pareceriam iguais."""
    panel = compute_panel(_serie(count=25), IndicatorSelection(sma_periods=(200,)))
    assert not panel.overlays
    assert "SMA(200)" in panel.failures
    assert "exige ao menos 200" in panel.failures["SMA(200)"]


def test_vwap_em_diario_falha_com_motivo_claro() -> None:
    panel = compute_panel(
        _serie(timeframe=Timeframe.D1), IndicatorSelection(vwap=True)
    )
    assert "VWAP" in panel.failures
    assert "intradiario" in panel.failures["VWAP"]


def test_bollinger_respeita_os_desvios() -> None:
    estreita = compute_panel(
        _serie(), IndicatorSelection(bollinger_period=20, bollinger_deviations=1.0)
    ).overlays["BB(20)"]
    larga = compute_panel(
        _serie(), IndicatorSelection(bollinger_period=20, bollinger_deviations=3.0)
    ).overlays["BB(20)"]
    assert larga.last()["upper"] > estreita.last()["upper"]


def test_macd_usa_os_parametros_informados() -> None:
    panel = compute_panel(
        _serie(), IndicatorSelection(macd=True, macd_fast=5, macd_slow=13, macd_signal=4)
    )
    assert panel.oscillators["MACD"].params == {"fast": 5.0, "slow": 13.0, "signal": 4.0}


def test_resultados_ficam_alinhados_a_serie() -> None:
    serie = _serie()
    panel = compute_panel(
        serie, IndicatorSelection(sma_periods=(20,), rsi_period=14, atr_period=14)
    )
    for resultado in {**panel.overlays, **panel.oscillators}.values():
        assert len(resultado.values) == len(serie)


def test_panel_vazio_por_padrao() -> None:
    from cashinho.pipeline.indicators import IndicatorPanel

    assert not IndicatorPanel().has_content


@pytest.mark.parametrize("period", [9, 20, 50])
def test_sma_de_periodos_variados(period: int) -> None:
    panel = compute_panel(_serie(count=120), IndicatorSelection(sma_periods=(period,)))
    assert panel.overlays[f"SMA({period})"].warmup == period - 1
