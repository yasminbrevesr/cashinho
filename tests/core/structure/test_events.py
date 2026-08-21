"""Rompimento, possivel falso rompimento e pullback."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.structure import EstruturaConfig, TipoEvento, analisar_estrutura
from cashinho.models import Candle, Direction, Series

from .factories import serie_zigzag

CFG = EstruturaConfig()


def _eventos(estrutura, tipo):
    return estrutura.eventos_do_tipo(tipo)


def test_fechar_acima_da_zona_e_rompimento():
    """Duas rejeicoes em 31,00 formam a resistencia; depois o preco fecha em 31,80."""
    serie, _ = serie_zigzag([30.0, 31.0, 30.3, 31.0, 30.4, 31.8])
    e = analisar_estrutura(serie, CFG)

    rompimentos = _eventos(e, TipoEvento.ROMPIMENTO)
    assert rompimentos, "o fechamento acima da zona precisa virar rompimento"
    r = rompimentos[-1]
    assert r.direcao is Direction.LONG
    assert r.nivel.low <= 31.05
    assert r.preco > r.nivel.high
    assert 0.0 < r.forca <= 1.0


def test_romper_e_voltar_vira_possivel_falso_rompimento():
    serie, _ = serie_zigzag([30.0, 31.0, 30.3, 31.0, 30.4, 31.5, 30.6])
    e = analisar_estrutura(serie, CFG)

    falsos = _eventos(e, TipoEvento.POSSIVEL_FALSO_ROMPIMENTO)
    assert falsos, "romper e devolver precisa ser sinalizado"
    f = falsos[-1]
    assert "falso rompimento" in f.descricao
    assert f.detalhes["candle_retorno"] > f.detalhes["candle_rompimento"]


def test_sombra_que_fura_e_volta_no_mesmo_candle_e_rejeicao():
    serie, _ = serie_zigzag([30.0, 31.0, 30.3, 31.0, 30.5])
    ultimo = serie.last
    # candle que espeta 31,40 e fecha de volta em 30,60
    espeto = Candle(
        ts=ultimo.ts + timedelta(minutes=5),
        open=30.5,
        high=31.4,
        low=30.45,
        close=30.6,
        volume=30_000.0,
    )
    com_espeto = Series(serie.symbol, serie.timeframe, serie.candles + [espeto])

    e = analisar_estrutura(com_espeto, CFG)
    falsos = _eventos(e, TipoEvento.POSSIVEL_FALSO_ROMPIMENTO)

    assert any(f.detalhes.get("tipo_rejeicao") == "sombra" for f in falsos)


def test_nivel_distante_nao_gera_rompimento_fantasma():
    """Suporte bem abaixo do preco nao pode ser 'rompido' so por estar abaixo."""
    serie, _ = serie_zigzag([30.0, 31.0, 30.2, 32.0, 31.2, 33.0])
    e = analisar_estrutura(serie, CFG)

    for evento in _eventos(e, TipoEvento.ROMPIMENTO):
        assert evento.nivel is not None
        # o candle do evento precisa ter cruzado a zona, nao apenas estar longe dela
        assert evento.nivel.low - e.atr <= evento.preco <= evento.nivel.high + 3 * e.atr


def test_zona_recem_formada_nao_pode_ser_rompida_pelo_proprio_candle():
    serie, _ = serie_zigzag([30.0, 31.0, 30.3, 31.8])
    e = analisar_estrutura(serie, CFG)

    for evento in _eventos(e, TipoEvento.ROMPIMENTO):
        formado_ate = max(evento.nivel.pivos) + CFG.pivo_direita
        assert evento.indice > formado_ate


def test_correcao_a_favor_da_tendencia_vira_pullback():
    """Alta de 30 a 33 e devolucao ate ~31,5 (50% da ultima perna)."""
    serie, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0, 32.2])
    e = analisar_estrutura(serie, CFG)

    pb = e.pullback
    assert pb is not None, "correcao dentro da tendencia precisa virar pullback"
    assert pb.direcao is Direction.LONG
    assert CFG.pullback_min <= pb.detalhes["retracao"] <= CFG.pullback_max
    assert "corrigindo" in pb.descricao


def test_pullback_deixa_de_valer_quando_a_perna_e_devolvida_inteira():
    serie, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0, 31.0])
    e = analisar_estrutura(serie, CFG)

    if e.swing_valido and e.swing_valido.eh_alta:
        retracao = e.swing_valido.retracao_em(e.preco)
        if retracao and retracao > CFG.pullback_max:
            assert e.pullback is None


def test_lateralizacao_nao_produz_pullback():
    serie, _ = serie_zigzag([30.0, 31.0, 30.0, 31.0, 30.0, 30.5])
    e = analisar_estrutura(serie, CFG)

    assert e.pullback is None


def test_janela_de_eventos_e_configuravel():
    serie, _ = serie_zigzag([30.0, 31.0, 30.3, 31.0, 30.4, 31.8, 32.0, 32.2, 32.4])
    curta = analisar_estrutura(serie, EstruturaConfig(janela_eventos=1))
    longa = analisar_estrutura(serie, EstruturaConfig(janela_eventos=30))

    assert len(longa.eventos) >= len(curta.eventos)
