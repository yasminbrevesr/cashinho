"""Tendencia de alta, de baixa e lateralizacao."""

from __future__ import annotations

from cashinho.core.structure import EstruturaConfig, Regime, analisar_estrutura

from .factories import serie_zigzag

CFG = EstruturaConfig()


def test_topos_e_fundos_ascendentes_viram_tendencia_de_alta():
    serie, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0])
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.ALTA
    assert e.tendencia.sequencia == "HH/HL"
    assert e.tendencia.forca > 0.5
    assert "alta" in e.tendencia.descricao


def test_topos_e_fundos_descendentes_viram_tendencia_de_baixa():
    serie, _ = serie_zigzag([33.0, 32.0, 32.4, 31.0, 31.4, 30.0])
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.BAIXA
    assert e.tendencia.sequencia == "LH/LL"
    assert e.tendencia.direcao.value == "VENDA"


def test_topos_e_fundos_no_mesmo_lugar_viram_lateralizacao():
    serie, _ = serie_zigzag([30.0, 31.0, 30.0, 31.0, 30.0, 31.0])
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.LATERAL
    assert e.tendencia.sequencia == "=H/=L"
    assert "lateralizacao" in e.tendencia.descricao
    assert e.tendencia.range_low is not None and e.tendencia.range_high is not None


def test_expansao_de_volatilidade_nao_e_tendencia():
    """Topo mais alto com fundo mais fundo (HH/LL) e' expansao, nao tendencia."""
    serie, _ = serie_zigzag([31.0, 32.0, 30.5, 33.0, 29.5, 33.5])
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.LATERAL
    assert e.tendencia.sequencia == "HH/LL"
    assert "expansao" in e.tendencia.descricao


def test_compressao_tambem_e_lateralizacao():
    """Topos descendo e fundos subindo (LH/HL) formam triangulo."""
    serie, _ = serie_zigzag([30.0, 33.0, 30.5, 32.5, 31.0, 32.0])
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.LATERAL
    assert e.tendencia.sequencia == "LH/HL"
    assert "triangulo" in e.tendencia.descricao


def test_estrutura_insuficiente_nao_inventa_tendencia():
    serie, _ = serie_zigzag([30.0, 31.0], passos=4)
    e = analisar_estrutura(serie, CFG)

    assert e.tendencia.regime is Regime.LATERAL
    assert e.tendencia.forca == 0.0
    assert "insuficiente" in e.tendencia.descricao


def test_topo_e_fundo_atuais_sao_os_swings_mais_recentes():
    serie, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0])
    e = analisar_estrutura(serie, CFG)

    assert e.topo is e.swing_highs[-1]
    assert e.fundo is e.swing_lows[-1]
    assert e.topo.preco > e.fundo.preco
