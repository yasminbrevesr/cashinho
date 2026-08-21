"""Suportes e resistencias."""

from __future__ import annotations

import pytest

from cashinho.core.structure import EstruturaConfig, analisar_estrutura

from .factories import serie_zigzag

CFG = EstruturaConfig()


def test_precos_testados_varias_vezes_viram_uma_zona_com_varios_toques():
    """O preco bate tres vezes na regiao de 31,00: uma zona, tres toques."""
    serie, _ = serie_zigzag([30.0, 31.0, 30.2, 31.0, 30.2, 31.0, 30.4])
    e = analisar_estrutura(serie, CFG)

    zonas = e.suportes + e.resistencias + ([e.zona_atual] if e.zona_atual else [])
    perto_de_31 = [z for z in zonas if z.low <= 31.02 <= z.high + 0.05]
    assert perto_de_31, "a regiao de 31,00 precisa virar zona"
    assert max(z.toques for z in perto_de_31) >= 2


def test_zona_acima_do_preco_e_resistencia_e_abaixo_e_suporte():
    serie, _ = serie_zigzag([30.0, 32.0, 30.5, 32.0, 31.0])
    e = analisar_estrutura(serie, CFG)

    assert all(z.low > e.preco or z.contem(e.preco) for z in e.resistencias)
    assert all(z.high < e.preco or z.contem(e.preco) for z in e.suportes)
    assert all(z.tipo == "resistencia" for z in e.resistencias)
    assert all(z.tipo == "suporte" for z in e.suportes)


def test_zonas_saem_ordenadas_da_mais_proxima_para_a_mais_distante():
    serie, _ = serie_zigzag([30.0, 31.0, 30.2, 32.0, 30.6, 33.0, 31.5])
    e = analisar_estrutura(serie, CFG)

    distancias_sup = [z.distancia(e.preco) for z in e.suportes]
    distancias_res = [z.distancia(e.preco) for z in e.resistencias]
    assert distancias_sup == sorted(distancias_sup)
    assert distancias_res == sorted(distancias_res)


def test_forca_da_zona_cresce_com_o_numero_de_toques():
    tres_toques, _ = serie_zigzag([30.0, 31.0, 30.2, 31.0, 30.2, 31.0, 30.4])
    um_toque, _ = serie_zigzag([30.0, 31.0, 30.4])

    e3 = analisar_estrutura(tres_toques, CFG)
    e1 = analisar_estrutura(um_toque, CFG)

    def forca_perto_de_31(e):
        zonas = e.suportes + e.resistencias + ([e.zona_atual] if e.zona_atual else [])
        candidatas = [z for z in zonas if z.low <= 31.05 and z.high >= 30.95]
        return max((z.forca for z in candidatas), default=0.0)

    assert forca_perto_de_31(e3) > forca_perto_de_31(e1)


def test_numero_de_zonas_por_lado_e_configuravel():
    serie, _ = serie_zigzag([30.0, 31.0, 30.2, 32.0, 30.6, 33.0, 30.8, 34.0, 31.2])
    e = analisar_estrutura(serie, EstruturaConfig(max_niveis_por_lado=2))

    assert len(e.suportes) <= 2
    assert len(e.resistencias) <= 2


def test_zona_que_contem_o_preco_vira_zona_atual():
    serie, _ = serie_zigzag([30.0, 31.0, 30.0, 31.0, 30.98])
    e = analisar_estrutura(serie, CFG)

    if e.zona_atual is not None:
        assert e.zona_atual.contem(e.preco)
        assert e.zona_atual not in e.suportes and e.zona_atual not in e.resistencias
