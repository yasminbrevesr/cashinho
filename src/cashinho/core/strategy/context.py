"""O que uma estrategia recebe para trabalhar.

O contexto chega pronto e limpo: a serie ja vem so com candles FECHADOS (e'
o que a vista do motor multi-timeframe entrega), entao a estrategia nao tem
como espiar o futuro nem precisa se preocupar com isso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ...models import Series


@dataclass(frozen=True)
class StrategyContext:
    """Dados de entrada de uma avaliacao."""

    symbol: str
    serie: Series  # timeframe de operacao, so candles fechados
    serie_tendencia: Optional[Series] = None  # timeframe maior, opcional
    estrutura: Any = None  # MarketStructure, quando disponivel
    extras: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.serie) == 0:
            raise ValueError("contexto sem candles: nao ha o que avaliar")

    @property
    def timeframe(self) -> str:
        return self.serie.timeframe

    @property
    def timestamp(self) -> datetime:
        """Fechamento do ultimo candle - o instante a que o sinal se refere."""
        return self.serie.last.ts

    @property
    def preco(self) -> float:
        return self.serie.price

    def tem_candles(self, minimo: int) -> bool:
        return len(self.serie) >= minimo


def de_vista(
    vista,
    symbol: str = "",
    papel_setup: str = "setup",
    papel_tendencia: Optional[str] = "tendencia",
) -> StrategyContext:
    """Monta o contexto a partir de uma vista do motor multi-timeframe.

        contexto = de_vista(engine.em(agora))
        sinal = estrategia.avaliar(contexto)

    A vista so devolve candles fechados, entao o sinal sai livre de lookahead.
    """
    serie = vista.serie_da_camada(papel_setup)
    superior = None
    if papel_tendencia:
        try:
            superior = vista.serie_da_camada(papel_tendencia)
        except Exception:  # camada ainda sem candle fechado
            superior = None
    return StrategyContext(
        symbol=symbol or serie.symbol,
        serie=serie,
        serie_tendencia=superior,
        extras={"instante": vista.instante, "vista": vista},
    )
