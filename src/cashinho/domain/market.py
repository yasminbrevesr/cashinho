"""Dados de mercado: candles e cotacoes.

Decisao arquitetural D4: o invariante de "candle fechado" e imposto pelo
tipo, nao por convencao. `CandleSeries.require_closed()` levanta excecao
em vez de deixar a disciplina a cargo de quem chama.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Self

import pandas as pd
from pydantic import Field, model_validator

from cashinho.domain.enums import Timeframe
from cashinho.domain.errors import LookaheadError, UnclosedCandleError
from cashinho.domain.types import DomainModel, Price, UtcDatetime

if TYPE_CHECKING:  # pragma: no cover
    from cashinho.ports.clock import Clock


class Candle(DomainModel):
    """Um candle OHLCV.

    `open_time` e o inicio do periodo, `close_time` o fim. `is_closed`
    indica se o periodo ja se encerrou no momento da coleta.
    """

    open_time: UtcDatetime
    close_time: UtcDatetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int = Field(ge=0)
    trades: int | None = Field(default=None, ge=0)
    is_closed: bool = True

    @model_validator(mode="after")
    def _validate_ohlc(self) -> Self:
        if self.close_time <= self.open_time:
            raise ValueError(
                f"close_time ({self.close_time.isoformat()}) deve ser posterior "
                f"a open_time ({self.open_time.isoformat()})"
            )
        if self.high < max(self.open, self.close):
            raise ValueError("high nao pode ser menor que open ou close")
        if self.low > min(self.open, self.close):
            raise ValueError("low nao pode ser maior que open ou close")
        if self.high < self.low:
            raise ValueError("high nao pode ser menor que low")
        return self

    @property
    def timestamp(self) -> datetime:
        """Instante de referencia do candle: o inicio do periodo.

        Nome explicito porque "timestamp de candle" e ambiguo entre
        abertura e fechamento — ambiguidade que desloca sinais em um
        periodo inteiro quando duas fontes discordam.
        """
        return self.open_time

    @property
    def range(self) -> Price:
        """Amplitude do candle."""
        return self.high - self.low


class CandleSeries(DomainModel):
    """Serie ordenada de candles de um ativo em um timeframe.

    Metadados de origem (`source`, `fetched_at`) acompanham a serie por
    exigencia de auditoria: nenhum dado circula no sistema sem procedencia.
    """

    symbol: str
    timeframe: Timeframe
    candles: tuple[Candle, ...] = ()
    source: str = Field(description="Identificador do provider de origem")
    fetched_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_ordering(self) -> Self:
        seen: set[datetime] = set()
        previous: datetime | None = None
        for candle in self.candles:
            if candle.open_time in seen:
                raise ValueError(
                    f"candle duplicado em {candle.open_time.isoformat()} "
                    f"para {self.symbol} {self.timeframe}"
                )
            if previous is not None and candle.open_time <= previous:
                raise ValueError(
                    "serie fora de ordem cronologica em "
                    f"{candle.open_time.isoformat()} para {self.symbol}"
                )
            seen.add(candle.open_time)
            previous = candle.open_time

        open_candles = [c for c in self.candles[:-1] if not c.is_closed]
        if open_candles:
            raise ValueError(
                "apenas o ultimo candle da serie pode estar aberto; "
                f"encontrados {len(open_candles)} candles abertos anteriores"
            )
        return self

    def __len__(self) -> int:
        return len(self.candles)

    @property
    def is_empty(self) -> bool:
        return not self.candles

    @property
    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    @property
    def has_open_candle(self) -> bool:
        return bool(self.candles) and not self.candles[-1].is_closed

    def closed_only(self) -> CandleSeries:
        """Retorna a serie sem o candle em formacao.

        Este e o unico caminho autorizado para alimentar indicadores e
        motores de decisao que exigem fechamento.
        """
        if not self.has_open_candle:
            return self
        return self.model_copy(update={"candles": self.candles[:-1]})

    def require_closed(self) -> CandleSeries:
        """Exige que a serie ja esteja integralmente fechada.

        Diferente de `closed_only()`, nao descarta silenciosamente: falha.
        Usar quando descartar o ultimo candio seria mascarar um erro de
        orquestracao do pipeline.
        """
        if self.has_open_candle:
            raise UnclosedCandleError(
                f"{self.symbol} {self.timeframe}: serie contem candle em formacao "
                f"({self.candles[-1].open_time.isoformat()}); "
                "a regra exige candle fechado"
            )
        return self

    def assert_no_lookahead(self, clock: Clock) -> CandleSeries:
        """Garante que nenhum candle fechado esta no futuro do relogio.

        Este e o teste central contra look-ahead bias. Em REPLAY e
        BACKTEST o relogio avanca artificialmente; qualquer candle com
        fechamento posterior ao instante logico e informacao que o
        algoritmo nao poderia conhecer.
        """
        now = clock.now()
        for candle in self.candles:
            if candle.is_closed and candle.close_time > now:
                raise LookaheadError(
                    f"{self.symbol} {self.timeframe}: candle fechado em "
                    f"{candle.close_time.isoformat()} e posterior ao instante "
                    f"logico do sistema ({now.isoformat()})"
                )
        return self

    def to_records(self) -> list[dict[str, object]]:
        """Representacao plana: um registro por candle, com os nove campos.

        `symbol`, `timeframe` e `source` sao atributos da serie, nao de
        cada candle — repeti-los em milhares de linhas gastaria memoria e
        permitiria estados incoerentes (candles de ativos diferentes na
        mesma serie). Esta projecao existe para os casos em que a forma
        plana e necessaria: exportacao, CSV e persistencia.
        """
        return [
            {
                "symbol": self.symbol,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "timeframe": self.timeframe.value,
                "source": self.source,
            }
            for candle in self.candles
        ]

    def to_frame(self) -> pd.DataFrame:
        """Converte para DataFrame indexado por open_time (UTC).

        Unica ponte autorizada entre o dominio (Decimal) e o pipeline
        numerico (float). A conversao e explicita e acontece so aqui.
        """
        if not self.candles:
            frame = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume", "is_closed"]
            )
            frame.index = pd.DatetimeIndex([], tz="UTC", name="open_time")
            return frame

        frame = pd.DataFrame(
            {
                "open": [float(c.open) for c in self.candles],
                "high": [float(c.high) for c in self.candles],
                "low": [float(c.low) for c in self.candles],
                "close": [float(c.close) for c in self.candles],
                "volume": [c.volume for c in self.candles],
                "is_closed": [c.is_closed for c in self.candles],
            },
            index=pd.DatetimeIndex(
                [c.open_time for c in self.candles], tz="UTC", name="open_time"
            ),
        )
        return frame


class Quote(DomainModel):
    """Cotacao pontual.

    `latency_ms` e `source` sao obrigatorios: uma cotacao sem procedencia
    e sem idade nao pode ser usada para decisao ao vivo.
    """

    symbol: str
    price: Price
    timestamp: UtcDatetime
    source: str
    latency_ms: int | None = Field(default=None, ge=0)
    bid: Price | None = None
    ask: Price | None = None

    def age_seconds(self, clock: Clock) -> float:
        """Idade da cotacao em relacao ao instante logico do sistema."""
        return (clock.now() - self.timestamp).total_seconds()
