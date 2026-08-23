"""Os filtros iniciais - cortar barato antes de analisar caro."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.scanner import ScannerConfig, aplicar
from cashinho.core.scanner.filtros import (
    dados_disponiveis,
    liquidez,
    spread,
    volatilidade,
    volume,
)

from .factories import (
    ABERTURA,
    serie,
    serie_curta,
    serie_liquida,
    serie_parada,
    serie_sem_liquidez,
)

CFG = ScannerConfig(candles_minimos=120, liquidez_minima_diaria=1_000_000.0,
                    atr_min_pct=0.05, atr_max_pct=3.0)


def test_os_cinco_filtros_pedidos_rodam():
    resultados = aplicar(serie_liquida(), CFG, spread_ticks=1.0)

    assert {f.chave for f in resultados} == {"dados", "liquidez", "volume",
                                             "volatilidade", "spread"}


# --- disponibilidade de dados ---------------------------------------------------


def test_serie_curta_e_cortada():
    f = dados_disponiveis(serie_curta(), CFG)

    assert f.passou is False
    assert "minimo 120" in f.detalhe


def test_serie_completa_passa():
    assert dados_disponiveis(serie_liquida(), CFG).passou is True


def test_dado_atrasado_e_cortado_quando_o_limite_esta_ligado():
    cfg = ScannerConfig(atraso_maximo_minutos=15.0, atr_min_pct=0.05)
    s = serie_liquida()
    agora = s.last.ts + timedelta(minutes=60)

    assert dados_disponiveis(s, cfg, agora).passou is False
    assert dados_disponiveis(s, cfg, s.last.ts + timedelta(minutes=5)).passou is True


def test_sem_limite_de_atraso_o_filtro_nao_reclama():
    s = serie_liquida()
    agora = s.last.ts + timedelta(days=3)

    assert dados_disponiveis(s, CFG, agora).passou is True


# --- liquidez ----------------------------------------------------------------------


def test_papel_sem_liquidez_e_cortado():
    f = liquidez(serie_sem_liquidez(), CFG)

    assert f.passou is False
    assert "abaixo do minimo" in f.detalhe


def test_papel_liquido_passa():
    f = liquidez(serie_liquida(), CFG)

    assert f.passou is True
    assert f.valor > CFG.liquidez_minima_diaria


# --- volume -------------------------------------------------------------------------


def test_ativo_parado_agora_e_cortado_pelo_volume():
    n = 300
    volumes = [200_000.0] * (n - 20) + [1_000.0] * 20  # secou no fim
    s = serie([30.0 * 1.0004 ** i for i in range(n)], volumes=volumes)

    f = volume(s, CFG)
    assert f.passou is False
    assert "papel parado agora" in f.detalhe


def test_volume_normal_passa():
    assert volume(serie_liquida(), CFG).passou is True


def test_serie_curta_nao_permite_checar_volume():
    f = volume(serie_curta(), CFG)

    assert f.verificado is False


# --- volatilidade ----------------------------------------------------------------------


def test_ativo_parado_e_cortado_pela_volatilidade():
    f = volatilidade(serie_parada(), CFG)

    assert f.passou is False
    assert "abaixo do minimo" in f.detalhe


def test_volatilidade_excessiva_e_cortada():
    cfg = ScannerConfig(atr_max_pct=0.1, atr_min_pct=0.01)
    f = volatilidade(serie_liquida(), cfg)

    assert f.passou is False
    assert "acima do maximo" in f.detalhe


def test_volatilidade_na_faixa_passa():
    assert volatilidade(serie_liquida(), CFG).passou is True


# --- spread -------------------------------------------------------------------------------


def test_spread_sem_book_fica_nao_verificado():
    f = spread(serie_liquida(), CFG, None, None)

    assert f.verificado is False
    assert "sem book" in f.detalhe
    assert f.passou is True  # nao corta, mas tambem nao conta como checado


def test_spread_largo_corta():
    f = spread(serie_liquida(), CFG, None, ticks=8.0)

    assert f.passou is False
    assert "acima do maximo" in f.detalhe


def test_spread_apertado_passa():
    f = spread(serie_liquida(), CFG, None, ticks=1.0)

    assert f.passou is True and f.verificado is True
