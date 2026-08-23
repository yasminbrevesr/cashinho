"""A fita de mercado: os candles passam um a um, e o futuro nao existe.

Esta e' a peca que sustenta o replay inteiro. Ela guarda a serie completa -
alguem precisa guardar -, mas **nao entrega** nada alem da posicao atual.
Quem receber a fita nao tem como espiar: tentar ler um candle a frente
levanta ``LookaheadError``, e ``visivel()`` devolve so o passado.

Nao ha metodo para ver o futuro. Nao e' uma questao de disciplina de quem
chama; nao existe caminho.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional, Sequence

from ...models import Candle, Series
from ..mtf.errors import LookaheadError


class FitaDeMercado:
    """A serie sendo revelada candle a candle."""

    def __init__(self, serie: Series, posicao: int = -1):
        if len(serie) == 0:
            raise ValueError("fita sem candles")
        self._serie = serie
        self._posicao = max(posicao, -1)

    # ------------------------------------------------------------------
    @property
    def symbol(self) -> str:
        return self._serie.symbol

    @property
    def timeframe(self) -> str:
        return self._serie.timeframe

    @property
    def posicao(self) -> int:
        """Indice do candle atual. -1 = a fita ainda nao comecou."""
        return self._posicao

    @property
    def comecou(self) -> bool:
        return self._posicao >= 0

    @property
    def terminou(self) -> bool:
        return self._posicao >= len(self._serie) - 1

    @property
    def total(self) -> int:
        """Quantos candles a fita tem no total - contagem, nunca preco."""
        return len(self._serie)

    @property
    def restantes(self) -> int:
        return len(self._serie) - 1 - self._posicao

    @property
    def progresso(self) -> float:
        return (self._posicao + 1) / len(self._serie) if len(self._serie) else 0.0

    # ------------------------------------------------------------------
    @property
    def atual(self) -> Candle:
        """O candle que acabou de fechar."""
        if not self.comecou:
            raise LookaheadError("a fita ainda nao comecou: nenhum candle fechou")
        return self._serie.candles[self._posicao]

    @property
    def instante(self) -> datetime:
        """O 'agora' do replay - o fechamento do candle atual."""
        return self.atual.ts

    def avancar(self) -> Candle:
        """Revela o proximo candle."""
        if self.terminou:
            raise StopIteration("a fita acabou")
        self._posicao += 1
        return self.atual

    def visivel(self) -> Series:
        """A serie ate agora - so o que ja fechou."""
        fim = self._posicao + 1
        return Series(self._serie.symbol, self._serie.timeframe, self._serie.candles[:fim])

    def candle(self, indice: int) -> Candle:
        """Um candle do passado. Pedir um do futuro e' erro, nao aviso."""
        if indice < 0:
            indice = self._posicao + 1 + indice
        if indice > self._posicao:
            raise LookaheadError(
                f"candle {indice} ainda nao aconteceu (a fita esta em {self._posicao}): "
                "ler o futuro invalidaria o replay inteiro"
            )
        if indice < 0:
            raise IndexError(f"candle {indice} fora da fita")
        return self._serie.candles[indice]

    def __getitem__(self, indice: int) -> Candle:
        return self.candle(indice)

    def __len__(self) -> int:
        """Quantos candles ja passaram."""
        return self._posicao + 1

    def __iter__(self) -> Iterator[Candle]:
        """Percorre o que ja passou - nunca o que falta."""
        return iter(self._serie.candles[: self._posicao + 1])

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        estado = f"{self._posicao + 1}/{len(self._serie)}"
        return f"<FitaDeMercado {self._serie.symbol} {self._serie.timeframe} {estado}>"


def fita_do_dia(serie: Series, dia: Optional[date] = None) -> FitaDeMercado:
    """Recorta um pregao da serie e devolve a fita daquele dia."""
    if dia is None:
        return FitaDeMercado(serie)
    candles = [c for c in serie.candles if c.ts.date() == dia]
    if not candles:
        raise ValueError(f"nenhum candle de {serie.symbol} em {dia:%d/%m/%Y}")
    return FitaDeMercado(Series(serie.symbol, serie.timeframe, candles))


def dias_disponiveis(serie: Series) -> list[date]:
    return sorted({c.ts.date() for c in serie.candles})
