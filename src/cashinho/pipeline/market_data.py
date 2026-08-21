"""Orquestracao da carga de dados de mercado.

Ponto unico onde provider, capacidade declarada e portao de qualidade se
encontram. A interface chama esta funcao; nao monta a sequencia sozinha.

Motivo: se cada tela repetisse "carrega, valida, decide", a regra de
bloqueio existiria em varias copias e uma delas acabaria desatualizada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cashinho.core.data_quality.gate import DEFAULT_MINIMUM_CANDLES, evaluate
from cashinho.domain.enums import DataStatus, Mode, Timeframe
from cashinho.domain.market import CandleSeries
from cashinho.domain.quality import DataQualityReport
from cashinho.observability.logging import get_logger
from cashinho.ports.clock import Clock
from cashinho.ports.market_data import MarketDataProvider

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MarketDataResult:
    """Resultado de uma carga de dados.

    Carrega sempre a serie e o relatorio, mesmo quando bloqueada: a tela
    precisa explicar o motivo do bloqueio, e um retorno vazio esconderia
    a evidencia.
    """

    series: CandleSeries
    report: DataQualityReport
    provider: str
    mode: Mode
    rejection_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.report.blocked or self.rejection_reason is not None

    @property
    def usable_series(self) -> CandleSeries | None:
        """Serie apta a analise, ou None quando bloqueada."""
        return None if self.blocked else self.series.closed_only()


def load_market_data(
    provider: MarketDataProvider,
    *,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    clock: Clock,
    mode: Mode = Mode.RESEARCH,
    minimum_candles: int = DEFAULT_MINIMUM_CANDLES,
) -> MarketDataResult:
    """Carrega candles e submete ao portao de qualidade.

    A checagem de capacidade acontece ANTES da carga: se o provedor nao
    serve ao modo ou ao timeframe, buscar o dado apenas para descartar
    depois seria desperdicio e daria a falsa impressao de que a fonte
    estava adequada.
    """
    capabilities = provider.capabilities
    rejection = capabilities.rejection_reason(mode, timeframe)
    if rejection is not None:
        logger.warning(
            "provider incompativel com o modo",
            extra={"symbol": symbol, "mode": mode.value, "reason": rejection},
        )
        empty = CandleSeries(
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=(),
            source=capabilities.name,
            fetched_at=clock.now(),
        )
        return MarketDataResult(
            series=empty,
            report=DataQualityReport.from_issues(
                symbol=symbol.upper(),
                source=capabilities.name,
                issues=(),
                checked_at=clock.now(),
            ).model_copy(update={"status": DataStatus.BLOCKED}),
            provider=capabilities.name,
            mode=mode,
            rejection_reason=rejection,
        )

    series = provider.get_candles(symbol, timeframe, start=start, end=end)
    report = evaluate(
        series,
        clock=clock,
        mode=mode,
        minimum_candles=minimum_candles,
    )
    return MarketDataResult(
        series=series,
        report=report,
        provider=capabilities.name,
        mode=mode,
    )
