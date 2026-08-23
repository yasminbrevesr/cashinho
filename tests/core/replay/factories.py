"""Series e replays para os testes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.replay import MarketReplay, ReplayConfig, Velocidade
from cashinho.core.replay.velocidade import Relogio
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)
DIA = ABERTURA.date()


def serie(closes: Sequence[float], symbol: str = "PETR4", timeframe: str = "1m",
          inicio: Optional[datetime] = None, pavio: float = 0.0015,
          volumes: Optional[Sequence[float]] = None) -> Series:
    inicio = inicio or ABERTURA
    candles = []
    anterior = closes[0]
    for i, c in enumerate(closes):
        candles.append(Candle(
            inicio + timedelta(minutes=i), anterior,
            max(anterior, c) * (1 + pavio), min(anterior, c) * (1 - pavio), c,
            volumes[i] if volumes else 20_000.0,
        ))
        anterior = c
    return Series(symbol, timeframe, candles)


def serie_alta(n: int = 200, passo: float = 0.0006, **kwargs) -> Series:
    return serie([30.0 * (1 + passo) ** i for i in range(n)], **kwargs)


def relogio_falso(velocidade: Velocidade = Velocidade.MAXIMA) -> Relogio:
    """Nao dorme de verdade - so anota quanto teria dormido."""
    dormidas: list[float] = []
    return Relogio(velocidade, dormir=dormidas.append), dormidas  # type: ignore[return-value]


def replay(serie_de_dados: Optional[Series] = None, **campos) -> MarketReplay:
    dados = serie_de_dados if serie_de_dados is not None else serie_alta()
    base = dict(symbol=dados.symbol, dia=None, velocidade=Velocidade.MAXIMA,
                minimo_para_analisar=30)
    base.update(campos)
    return MarketReplay(dados, ReplayConfig(**base))


def pregao(semente: int = 3, dia_indice: int = -1, dias: int = 4, **campos) -> MarketReplay:
    """Replay de um pregao sintetico - com movimento suficiente para o pipeline agir.

    A serie geometrica lisa de ``serie_alta`` nunca alinha as camadas, entao
    nao serve para os testes que precisam de oportunidade de verdade.
    """
    from cashinho.data.synthetic import SyntheticProvider

    serie_dados = SyntheticProvider(semente=semente).candles("PETR4", "1m", dias)
    todos = sorted({c.ts.date() for c in serie_dados.candles})
    base = dict(symbol="PETR4", dia=todos[dia_indice], velocidade=Velocidade.MAXIMA,
                minimo_para_analisar=30)
    base.update(campos)
    return MarketReplay(serie_dados, ReplayConfig(**base)), serie_dados
