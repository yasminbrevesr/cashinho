"""Estrutura lida a partir do motor multi-timeframe - sem lookahead."""

from __future__ import annotations

from datetime import timedelta

from cashinho.core.mtf import MTFConfig, MTFEngine
from cashinho.core.structure import analisar_camada, analisar_estrutura
from cashinho.models import BRT, Candle, Series

from .factories import serie_zigzag


def _serie_1m(n: int = 200) -> Series:
    """Zigzag reamostrado para 1m dentro do pregao."""
    base, _ = serie_zigzag(
        [30.0, 30.6, 30.3, 31.2, 30.9, 31.8, 31.4],
        passos=max(n // 6, 1),
        minutos=1,
    )
    return Series("PETR4", "1m", base.candles[:n])


def test_estrutura_da_camada_usa_apenas_candles_fechados():
    engine = MTFEngine(MTFConfig.padrao()).alimentar(_serie_1m(180))
    vista = engine.em(engine.agora().instante)

    estrutura = analisar_camada(vista, "setup")
    serie_fechada = vista.serie_da_camada("setup")

    assert estrutura.timeframe == "5m"
    assert estrutura.ts == serie_fechada.last.ts
    assert all(p.ts <= serie_fechada.last.ts for p in estrutura.pivos)


def test_pivo_nao_aparece_antes_do_candle_que_o_confirma():
    """A mesma serie, lida dois instantes diferentes, nao pode 'lembrar' do futuro."""
    serie = _serie_1m(180)
    engine = MTFEngine(MTFConfig.padrao()).alimentar(serie)

    vistas = list(engine.replay())
    for vista in vistas[::20]:
        if len(vista.fechados("5m")) < 10:
            continue
        estrutura = analisar_camada(vista, "setup")
        for pivo in estrutura.pivos:
            assert pivo.ts_confirmacao <= vista.instante


def test_leitura_progressiva_nunca_reescreve_o_passado():
    """Pivos ja confirmados continuam com o mesmo preco nas leituras seguintes."""
    serie = _serie_1m(180)
    engine = MTFEngine(MTFConfig.padrao()).alimentar(serie)

    vistos: dict[str, float] = {}
    for vista in engine.replay():
        if len(vista.fechados("5m")) < 12:
            continue
        for pivo in analisar_camada(vista, "setup").pivos:
            chave = pivo.ts.isoformat()
            if chave in vistos:
                assert vistos[chave] == pivo.preco
            else:
                vistos[chave] = pivo.preco
    assert vistos


def test_estrutura_de_camadas_diferentes_e_independente():
    engine = MTFEngine(MTFConfig.padrao()).alimentar(_serie_1m(200))
    vista = engine.agora()

    setup = analisar_camada(vista, "setup")
    gatilho = analisar_camada(vista, "gatilho")

    assert setup.timeframe == "5m"
    assert gatilho.timeframe == "1m"
    assert len(gatilho.pivos) >= len(setup.pivos)  # mais candles, mais pivos
