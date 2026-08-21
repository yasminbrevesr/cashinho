"""Pivos, swing highs/lows e o filtro de ruido."""

from __future__ import annotations

import pytest

from cashinho.core.structure import EstruturaConfig, TipoPivo
from cashinho.core.structure.pivots import (
    alterna,
    detecta_pivos,
    filtra_significativos,
    limiar_swing,
    monta_swings,
    ultimo_swing_valido,
)

from .factories import recorta, serie_zigzag

CFG = EstruturaConfig()


def test_pivos_caem_exatamente_nos_vertices_do_zigzag():
    serie, vertices = serie_zigzag([30.0, 31.0, 30.5, 32.0, 31.5, 33.0])
    pivos = detecta_pivos(serie, CFG)

    indices = sorted(p.indice for p in pivos)
    assert indices == [v for v in vertices if 2 <= v <= len(serie) - 3]


def test_topo_e_fundo_sao_classificados_pela_maxima_e_pela_minima():
    serie, vertices = serie_zigzag([30.0, 31.0, 30.5, 32.0])
    pivos = {p.indice: p for p in detecta_pivos(serie, CFG)}

    topo = pivos[vertices[1]]
    fundo = pivos[vertices[2]]
    assert topo.tipo is TipoPivo.TOPO
    assert topo.preco == pytest.approx(serie.candles[vertices[1]].high)
    assert fundo.tipo is TipoPivo.FUNDO
    assert fundo.preco == pytest.approx(serie.candles[vertices[2]].low)


def test_pivo_so_e_confirmado_depois_dos_candles_da_direita():
    serie, vertices = serie_zigzag([30.0, 31.0, 30.5, 32.0])
    cfg = EstruturaConfig(pivo_esquerda=2, pivo_direita=2)
    topo = next(p for p in detecta_pivos(serie, cfg) if p.indice == vertices[1])

    assert topo.indice_confirmacao == topo.indice + 2
    assert topo.ts_confirmacao == serie.candles[topo.indice + 2].ts
    assert topo.confirmado_em(topo.indice) is False
    assert topo.confirmado_em(topo.indice + 2) is True


def test_pivo_nao_aparece_enquanto_os_candles_de_confirmacao_nao_fecharam():
    """O topo do indice 3 nao existe para quem esta no candle 4."""
    serie, vertices = serie_zigzag([30.0, 31.0, 30.5, 32.0])
    topo = vertices[1]

    parcial = recorta(serie, topo + 2)  # candles 0..topo+1
    assert all(p.indice != topo for p in detecta_pivos(parcial, CFG))

    completa = recorta(serie, topo + 3)  # ja fechou o candle de confirmacao
    assert any(p.indice == topo for p in detecta_pivos(completa, CFG))


def test_numero_de_candles_de_confirmacao_e_configuravel():
    serie, _ = serie_zigzag([30.0, 31.0, 30.5, 32.0], passos=5)
    frouxo = detecta_pivos(serie, EstruturaConfig(pivo_esquerda=1, pivo_direita=1))
    rigoroso = detecta_pivos(serie, EstruturaConfig(pivo_esquerda=4, pivo_direita=4))

    assert len(frouxo) >= len(rigoroso)
    assert all(p.indice_confirmacao == p.indice + 4 for p in rigoroso)


def test_alternancia_colapsa_topos_seguidos_no_mais_alto():
    serie, vertices = serie_zigzag([30.0, 31.0, 30.9, 31.6, 30.2])
    pivos = detecta_pivos(serie, CFG)
    alternados = alterna(pivos)

    tipos = [p.tipo for p in alternados]
    assert all(a is not b for a, b in zip(tipos, tipos[1:])), "topos/fundos precisam se revezar"


def test_perna_menor_que_o_limiar_e_descartada_como_ruido():
    """Um repique de 5 centavos no meio de uma alta nao vira estrutura."""
    serie, _ = serie_zigzag([30.0, 31.0, 30.95, 32.0])
    limiar = limiar_swing(serie.price, 0.35, CFG)
    assert 0.05 < limiar  # o repique esta abaixo do limiar

    significativos = filtra_significativos(detecta_pivos(serie, CFG), serie.price, 0.35, CFG)
    precos = [round(p.preco, 2) for p in significativos]
    assert not any(30.90 <= p <= 31.00 for p in precos[1:-1])


def test_swings_recebem_amplitude_em_atr_e_em_percentual():
    serie, _ = serie_zigzag([30.0, 32.0, 31.0, 33.0])
    pivos = filtra_significativos(detecta_pivos(serie, CFG), serie.price, 0.35, CFG)
    swings = monta_swings(pivos, serie.price, 0.35, CFG)

    assert swings
    primeiro = swings[0]
    assert primeiro.amplitude == pytest.approx(abs(primeiro.fim.preco - primeiro.inicio.preco))
    assert primeiro.amplitude_atr == pytest.approx(primeiro.amplitude / 0.35, rel=1e-3)
    assert primeiro.amplitude_pct > 0
    assert primeiro.duracao == primeiro.fim.indice - primeiro.inicio.indice


def test_ultimo_swing_valido_ignora_pernas_pequenas():
    serie, _ = serie_zigzag([30.0, 32.0, 31.0, 33.0])
    pivos = filtra_significativos(detecta_pivos(serie, CFG), serie.price, 0.35, CFG)
    swings = monta_swings(pivos, serie.price, 0.35, CFG)

    grande = ultimo_swing_valido(swings)
    assert grande is not None and grande.valido

    # com um limiar absurdo, nenhuma perna passa
    cfg_rigoroso = EstruturaConfig(swing_min_atr=50.0)
    nenhum = monta_swings(pivos, serie.price, 0.35, cfg_rigoroso)
    assert ultimo_swing_valido(nenhum) is None


def test_serie_curta_nao_produz_pivos():
    serie, _ = serie_zigzag([30.0, 30.5], passos=1)
    assert detecta_pivos(serie, CFG) == []


def test_serie_vazia_e_recusada_com_mensagem_clara():
    import pytest as _pytest

    from cashinho.core.structure import analisar_estrutura
    from cashinho.models import Series

    with _pytest.raises(ValueError, match="vazia"):
        analisar_estrutura(Series("PETR4", "5m", []))


def test_serie_curta_devolve_estrutura_neutra_em_vez_de_quebrar():
    from cashinho.core.structure import analisar_estrutura

    serie, _ = serie_zigzag([30.0, 30.4], passos=1)
    e = analisar_estrutura(serie)

    assert e.pivos == []
    assert e.fib is None
    assert "insuficiente" in e.tendencia.descricao or "indisponivel" in e.tendencia.descricao
