"""Market Replay: o pregao de novo, candle a candle, sem futuro nenhum.

    from cashinho.core.replay import MarketReplay, ReplayConfig, Velocidade

    replay = MarketReplay(serie, ReplayConfig(symbol="PETR4", dia=dia,
                                              velocidade=Velocidade.X10))
    for passo in replay:
        print(pagina(replay))

A cada candle que fecha, o pipeline inteiro roda com **apenas o que existia
naquele instante**: fita -> multi-timeframe -> Strategy -> Opportunity ->
Score -> Auditor -> Risk Manager -> Paper Broker.
"""

from .eventos import EventoReplay, TipoEvento
from .fita import FitaDeMercado, dias_disponiveis, fita_do_dia
from .grafico import grafico
from .replay import EstadoReplay, MarketReplay, PassoReplay, ReplayConfig
from .velocidade import Relogio, Velocidade
from .view import (
    barra_de_progresso,
    cabecalho,
    pagina,
    painel_conta,
    painel_pipeline,
    painel_progresso,
    resumo,
    ultimos_eventos,
)

__all__ = [
    "MarketReplay",
    "ReplayConfig",
    "EstadoReplay",
    "PassoReplay",
    "FitaDeMercado",
    "fita_do_dia",
    "dias_disponiveis",
    "Velocidade",
    "Relogio",
    "EventoReplay",
    "TipoEvento",
    "grafico",
    "pagina",
    "cabecalho",
    "painel_progresso",
    "painel_pipeline",
    "painel_conta",
    "ultimos_eventos",
    "barra_de_progresso",
    "resumo",
]
