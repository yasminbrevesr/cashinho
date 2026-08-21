"""Timeframes e barras com janela explicita (inicio, fim).

Toda barra do motor carrega o intervalo que ela representa. E' isso que
permite responder, sem ambiguidade, a pergunta "esse candle ja fechou no
instante X?" - a base de toda a protecao contra lookahead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from ...models import Candle, Series
from .errors import ConfiguracaoInvalidaError

_PADRAO = re.compile(r"^\s*(\d+)\s*([mhd])\s*$", re.IGNORECASE)


@dataclass(frozen=True, order=False)
class Timeframe:
    """Um timeframe normalizado (ex.: ``5m``, ``60m``, ``1d``)."""

    rotulo: str
    minutos: int  # 0 quando a barra e' a sessao inteira (diario)
    sessao_inteira: bool = False

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return self.rotulo

    def duracao_minutos(self, minutos_da_sessao: int) -> int:
        return minutos_da_sessao if self.sessao_inteira else self.minutos

    def eh_multiplo_de(self, outro: "Timeframe") -> bool:
        if outro.sessao_inteira:
            return self.sessao_inteira
        if self.sessao_inteira:
            return True
        return self.minutos % outro.minutos == 0


def parse_timeframe(valor: str | Timeframe) -> Timeframe:
    """Converte ``"5m"``, ``"1h"``, ``"1d"`` em :class:`Timeframe`."""
    if isinstance(valor, Timeframe):
        return valor
    m = _PADRAO.match(str(valor))
    if not m:
        raise ConfiguracaoInvalidaError(
            f"timeframe invalido: {valor!r} (use algo como '1m', '5m', '15m', '60m', '1h', '1d')"
        )
    quantidade, unidade = int(m.group(1)), m.group(2).lower()
    if quantidade <= 0:
        raise ConfiguracaoInvalidaError(f"timeframe invalido: {valor!r}")
    if unidade == "d":
        if quantidade != 1:
            raise ConfiguracaoInvalidaError("apenas '1d' e' suportado no timeframe diario")
        return Timeframe("1d", 0, sessao_inteira=True)
    minutos = quantidade * (60 if unidade == "h" else 1)
    rotulo = f"{minutos}m"
    return Timeframe(rotulo, minutos)


def rotulo_canonico(valor: str | Timeframe) -> str:
    """``1h`` e ``60m`` viram o mesmo rotulo, para o usuario poder escrever os dois."""
    return parse_timeframe(valor).rotulo


@dataclass(frozen=True)
class Bar:
    """Um candle agregado com a janela que ele representa.

    ``inicio`` e' inclusivo e ``fim`` exclusivo: a barra passa a ser
    consultavel exatamente em ``fim``.
    """

    timeframe: str
    inicio: datetime
    fim: datetime
    candle: Candle
    n_base: int = 1
    dados_parciais: bool = False

    def fechada_em(self, ts: datetime) -> bool:
        """A barra ja fechou no instante ``ts``?"""
        return self.fim <= ts

    @property
    def ts(self) -> datetime:
        return self.candle.ts

    @property
    def close(self) -> float:
        return self.candle.close


def bars_para_series(symbol: str, timeframe: str, bars: Iterable[Bar]) -> Series:
    """Converte barras em :class:`Series`, o formato que os indicadores consomem."""
    return Series(symbol, timeframe, [b.candle for b in bars])


def agrega(candles: list[Candle], inicio: datetime) -> Optional[Candle]:
    """Agrega candles do timeframe base em um unico candle do timeframe maior."""
    if not candles:
        return None
    return Candle(
        ts=inicio,
        open=candles[0].open,
        high=max(c.high for c in candles),
        low=min(c.low for c in candles),
        close=candles[-1].close,
        volume=sum(c.volume for c in candles),
    )
