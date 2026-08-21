"""Series e estrategias de teste - tudo deterministico, sem random."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional, Sequence

from cashinho.core.strategy.base import Strategy
from cashinho.core.strategy.context import StrategyContext
from cashinho.core.strategy.models import Action, Signal
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 17, 10, 0, tzinfo=BRT)  # segunda-feira


def serie_1m(
    closes: Sequence[float],
    aberturas: Optional[Sequence[float]] = None,
    maximas: Optional[Sequence[float]] = None,
    minimas: Optional[Sequence[float]] = None,
    volumes: Optional[Sequence[float]] = None,
    inicio: Optional[datetime] = None,
    symbol: str = "PETR4",
) -> Series:
    """Serie de 1m a partir de listas explicitas - cada candle sob controle."""
    inicio = inicio or ABERTURA
    candles: list[Candle] = []
    anterior = (aberturas[0] if aberturas else closes[0])
    for i, fechamento in enumerate(closes):
        abertura = aberturas[i] if aberturas else anterior
        alta = maximas[i] if maximas else max(abertura, fechamento)
        baixa = minimas[i] if minimas else min(abertura, fechamento)
        candles.append(
            Candle(
                ts=inicio + timedelta(minutes=i),
                open=abertura,
                high=alta,
                low=baixa,
                close=fechamento,
                volume=(volumes[i] if volumes else 10_000.0),
            )
        )
        anterior = fechamento
    return Series(symbol, "1m", candles)


def serie_constante(n: int = 60, preco: float = 30.0, **kwargs) -> Series:
    return serie_1m([preco] * n, **kwargs)


class EstrategiaNoCandle(Strategy):
    """Emite um sinal quando a serie chega a um tamanho exato.

    Deixa o teste dizer, sem ambiguidade, EM QUAL candle a estrategia decidiu -
    que e' o que os testes de look-ahead precisam fixar.
    """

    nome = "teste-candle-fixo"
    experimental = False

    def __init__(
        self,
        emitir_em: int,
        action: Action = Action.BUY,
        entrada: float = 30.0,
        stop: float = 29.5,
        alvo: float = 31.0,
        repetir: bool = False,
    ):
        self.emitir_em = emitir_em
        self.action = action
        self.entrada = entrada
        self.stop = stop
        self.alvo = alvo
        self.repetir = repetir
        self.avaliacoes: list[tuple[int, datetime]] = []

    def avaliar(self, contexto: StrategyContext) -> Signal:
        n = len(contexto.serie)
        self.avaliacoes.append((n, contexto.serie.last.ts))
        emite = n == self.emitir_em or (self.repetir and n >= self.emitir_em)
        acao = self.action if emite else Action.WAIT
        return Signal(
            symbol=contexto.symbol,
            timestamp=contexto.timestamp,
            timeframe=contexto.timeframe,
            action=acao,
            setup="teste",
            confidence=1.0 if emite else 0.0,
            reasons=("teste",) if emite else (),
            invalidation="-",
            strategy=self.nome,
            niveis={
                "entrada_referencia": self.entrada,
                "stop_referencia": self.stop,
                "alvo_referencia": self.alvo,
            },
            experimental=False,
        )


class EstrategiaNunca(Strategy):
    """Nunca aciona nada - serve para testar o caso sem trade."""

    nome = "teste-nunca"
    experimental = False

    def avaliar(self, contexto: StrategyContext) -> Signal:
        return self.sinal_vazio(contexto, "sem condicao")
