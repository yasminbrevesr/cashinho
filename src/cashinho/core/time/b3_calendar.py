"""Sessao de negociacao da B3.

LIMITACOES DECLARADAS NESTA FASE
--------------------------------
1. Os horarios abaixo refletem o pregao regular de acoes e sao tratados
   como configuracao, nao como verdade absoluta. Horarios de leilao,
   after-market e derivativos NAO estao modelados.
2. NAO existe tabela de feriados embutida. Inventar um calendario de
   feriados produziria backtests silenciosamente errados. A lista e
   injetada por quem constroi o objeto e permanece vazia por padrao —
   `is_trading_day` retorna True para qualquer dia util enquanto a fonte
   oficial nao for integrada (Fase 2).

Interno sempre UTC; a conversao para o fuso local acontece aqui e na
camada de apresentacao.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from cashinho.domain.types import ensure_utc

B3_TIMEZONE = ZoneInfo("America/Sao_Paulo")

REGULAR_OPEN = time(10, 0)
REGULAR_CLOSE = time(17, 0)


class B3Calendar:
    """Calendario e sessao do pregao regular."""

    def __init__(
        self,
        *,
        holidays: frozenset[date] | None = None,
        open_time: time = REGULAR_OPEN,
        close_time: time = REGULAR_CLOSE,
    ) -> None:
        if close_time <= open_time:
            raise ValueError("close_time deve ser posterior a open_time")
        self.holidays = holidays or frozenset()
        self.open_time = open_time
        self.close_time = close_time

    @property
    def holidays_loaded(self) -> bool:
        """Se ha calendario de feriados carregado.

        Enquanto False, resultados que dependem de dias uteis devem ser
        tratados como aproximados e sinalizados na interface.
        """
        return bool(self.holidays)

    def to_local(self, instant: datetime) -> datetime:
        """Converte um instante UTC para o fuso da B3."""
        return ensure_utc(instant).astimezone(B3_TIMEZONE)

    def is_trading_day(self, day: date) -> bool:
        """Se a data e dia de pregao.

        Fim de semana sempre falso. Feriados dependem da lista injetada.
        """
        if day.weekday() >= 5:
            return False
        return day not in self.holidays

    def is_open(self, instant: datetime) -> bool:
        """Se o pregao regular esta aberto no instante informado."""
        local = self.to_local(instant)
        if not self.is_trading_day(local.date()):
            return False
        return self.open_time <= local.time() < self.close_time

    def session_bounds(self, day: date) -> tuple[datetime, datetime] | None:
        """Abertura e fechamento do pregao do dia, em UTC.

        Retorna None se nao houver pregao na data.
        """
        if not self.is_trading_day(day):
            return None
        start = datetime.combine(day, self.open_time, tzinfo=B3_TIMEZONE)
        end = datetime.combine(day, self.close_time, tzinfo=B3_TIMEZONE)
        return ensure_utc(start), ensure_utc(end)
