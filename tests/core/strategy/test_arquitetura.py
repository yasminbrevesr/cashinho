"""O que a primeira estrategia existe para provar: as pecas se encaixam.

dados -> motor multi-timeframe -> estrategia -> Signal -> tela -> risco,
sem que nenhuma peca precise conhecer o funcionamento da outra.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.mtf import MTFConfig, MTFEngine
from cashinho.core.risk import PedidoOperacao, RiskConfig, RiskManager
from cashinho.core.strategy import (
    Action,
    BaselineTendenciaVolumeATR,
    Signal,
    Strategy,
    StrategyContext,
    de_vista,
    disponiveis,
    obter,
    registrar,
)
from cashinho.core.strategy.base import _REGISTRO
from cashinho.models import BRT, Candle, Series

from .factories import INICIO, serie_alta


def _serie_1m(n: int = 400) -> Series:
    """A mesma alta da baseline, mas em candles de 1m dentro do pregao."""
    base = serie_alta(n=n)
    candles = [
        Candle(INICIO + timedelta(minutes=i), c.open, c.high, c.low, c.close, c.volume)
        for i, c in enumerate(base.candles)
    ]
    return Series("PETR4", "1m", candles)


# --- encaixe com o motor multi-timeframe -------------------------------------------


def test_estrategia_le_o_contexto_montado_a_partir_da_vista():
    engine = MTFEngine(MTFConfig.padrao()).alimentar(_serie_1m())
    vista = engine.agora()

    contexto = de_vista(vista)
    sinal = BaselineTendenciaVolumeATR().avaliar(contexto)

    assert isinstance(sinal, Signal)
    assert sinal.timeframe == "5m"
    assert sinal.timestamp == vista.serie_da_camada("setup").last.ts


def test_sinal_nunca_enxerga_candle_do_futuro():
    """Invariante herdada do motor: o sinal so conhece o que ja fechou."""
    engine = MTFEngine(MTFConfig.padrao()).alimentar(_serie_1m())
    estrategia = BaselineTendenciaVolumeATR()

    avaliados = 0
    for vista in list(engine.replay())[::25]:
        if len(vista.fechados("5m")) < 5:
            continue
        sinal = estrategia.avaliar(de_vista(vista))
        avaliados += 1
        assert sinal.timestamp <= vista.instante
    assert avaliados > 0


def test_contexto_funciona_mesmo_sem_a_camada_de_tendencia_fechada():
    engine = MTFEngine(MTFConfig.padrao()).alimentar(_serie_1m(n=60))
    contexto = de_vista(engine.em(engine.agora().instante))

    assert contexto.serie_tendencia is None or len(contexto.serie_tendencia) >= 0
    assert BaselineTendenciaVolumeATR().avaliar(contexto).action in set(Action)


# --- encaixe com o Risk Manager (a cola fica fora da estrategia) ---------------------


def test_sinal_acionavel_vira_pedido_para_o_risco_sem_a_estrategia_saber_do_risco():
    sinal = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_alta()))
    assert sinal.action is Action.BUY

    # quem traduz Signal -> PedidoOperacao e' a camada de fora, nao a estrategia
    pedido = PedidoOperacao(
        symbol=sinal.symbol,
        direcao=sinal.action.direcao,
        entrada=sinal.niveis["entrada_referencia"],
        stop=sinal.niveis["stop_referencia"],
        referencia=sinal.strategy,
    )
    rm = RiskManager(RiskConfig(capital=50_000))
    decisao = rm.avaliar(pedido)

    assert decisao.allowed is True
    assert decisao.position_size > 0


def test_o_risco_pode_recusar_um_sinal_de_alta_confianca():
    """Confianca da estrategia nao compra nada do risco."""
    sinal = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_alta()))
    rm = RiskManager(RiskConfig(capital=50_000))
    rm.acionar_kill_switch("teste de precedencia")

    decisao = rm.avaliar(
        PedidoOperacao("PETR4", sinal.action.direcao, sinal.niveis["entrada_referencia"],
                       sinal.niveis["stop_referencia"])
    )

    assert sinal.confidence > 0.6
    assert decisao.allowed is False


def test_a_estrategia_nao_importa_o_risk_manager():
    """Dependencia em uma direcao so: risco nao conhece estrategia, e vice-versa."""
    import inspect

    from cashinho.core.strategy import baseline

    fonte = inspect.getsource(baseline)
    assert "risk" not in fonte.lower().replace("risco por acao", "")


# --- registro de estrategias ----------------------------------------------------------


def test_a_baseline_esta_registrada():
    assert "baseline-tendencia" in disponiveis()
    assert isinstance(obter("baseline-tendencia"), BaselineTendenciaVolumeATR)


def test_estrategia_desconhecida_da_erro_com_a_lista():
    with pytest.raises(KeyError, match="baseline-tendencia"):
        obter("a-melhor-estrategia-do-mundo")


def test_uma_segunda_estrategia_encaixa_sem_mudar_nada_em_volta():
    """O teste que valida a arquitetura: outro algoritmo, mesmo contrato."""

    class SempreEspera(Strategy):
        nome = "teste-sempre-espera"
        descricao = "devolve WAIT para tudo"

        def avaliar(self, contexto: StrategyContext) -> Signal:
            return Signal(
                symbol=contexto.symbol,
                timestamp=contexto.timestamp,
                timeframe=contexto.timeframe,
                action=Action.WAIT,
                setup="nada por enquanto",
                confidence=0.0,
                reasons=(),
                invalidation="-",
                strategy=self.nome,
            )

    try:
        registrar(SempreEspera.nome, SempreEspera)
        sinal = obter("teste-sempre-espera").avaliar(StrategyContext("PETR4", serie_alta()))

        from cashinho.core.strategy import tela_analise

        assert sinal.action is Action.WAIT
        assert "PETR4" in tela_analise(sinal)  # a mesma tela serve para ela
    finally:
        _REGISTRO.pop("teste-sempre-espera", None)


def test_nome_repetido_no_registro_e_recusado():
    with pytest.raises(ValueError, match="ja existe"):
        registrar("baseline-tendencia", BaselineTendenciaVolumeATR)
