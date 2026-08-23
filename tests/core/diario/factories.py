"""Registros para os testes do diario."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.diario import DiarioDeTrades, Registro
from cashinho.models import BRT, Direction

BASE = datetime(2026, 8, 17, 10, 30, tzinfo=BRT)  # segunda-feira


def registro(
    resultado: float = 200.0,
    symbol: str = "PETR4",
    setup: str = "pullback a favor da tendencia",
    direcao: Direction = Direction.LONG,
    quando: Optional[datetime] = None,
    quantidade: int = 300,
    stop_distancia: float = 0.30,
    timeframe_setup: str = "5m",
    duracao_min: int = 30,
    score: float = 78.0,
    **campos,
) -> Registro:
    inicio = quando or BASE
    entrada = 31.00
    return Registro(
        symbol=symbol, direcao=direcao, aberta_em=inicio,
        fechada_em=inicio + timedelta(minutes=duracao_min),
        quantidade=quantidade, entrada=entrada,
        saida=entrada + resultado / quantidade,
        custos=campos.pop("custos", 3.0), resultado=resultado,
        stop=entrada - stop_distancia, alvo=entrada + stop_distancia * 2,
        setup=setup, score=score,
        timeframe_context="60m", timeframe_trend="15m",
        timeframe_setup=timeframe_setup, timeframe_trigger="1m",
        motivo_entrada=("camadas alinhadas", "gatilho com volume"),
        motivo_saida="alvo atingido" if resultado > 0 else "stop acionado",
        condicoes_de_mercado=("60m context: bullish", "15m trend: bullish"),
        warnings_auditor=() if resultado > 0 else ("risco/retorno apertado",),
        **campos,
    )


def diario(registros: Optional[Sequence[Registro]] = None) -> DiarioDeTrades:
    if registros is None:
        registros = [
            registro(200.0),
            registro(-90.0, symbol="VALE3"),
            registro(150.0, setup="rompimento com contexto", quando=BASE + timedelta(days=1)),
            registro(-90.0, setup="rompimento com contexto", quando=BASE + timedelta(days=1, hours=3)),
            registro(300.0, symbol="ITUB4", timeframe_setup="15m",
                     quando=BASE + timedelta(days=2)),
        ]
    return DiarioDeTrades(registros)
