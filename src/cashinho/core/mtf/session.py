"""Sessao de negociacao da B3.

O resample e' ancorado na abertura do pregao, e nao no relogio: um candle de
60m no mercado brasileiro vai das 10:00 as 11:00, nao das 00:00 as 01:00. O
ultimo balde do dia e' truncado no fim da sessao, de modo que nenhum candle
"fecha" depois que o pregao ja acabou.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from ...models import BRT


@dataclass(frozen=True)
class Sessao:
    """Janela diaria de negociacao."""

    abertura: time = time(10, 0)
    fechamento: time = time(17, 55)
    dias_uteis: frozenset[int] = field(default=frozenset({0, 1, 2, 3, 4}))
    feriados: frozenset[date] = field(default=frozenset())
    nome: str = "B3 - acoes"

    def eh_dia_util(self, dia: date) -> bool:
        return dia.weekday() in self.dias_uteis and dia not in self.feriados

    def limites(self, dia: date) -> tuple[datetime, datetime]:
        """(inicio, fim) da sessao naquele dia, no fuso de Brasilia."""
        inicio = datetime.combine(dia, self.abertura, tzinfo=BRT)
        fim = datetime.combine(dia, self.fechamento, tzinfo=BRT)
        return inicio, fim

    def contem(self, ts: datetime) -> bool:
        """True se o instante pertence ao pregao regular (fim exclusivo)."""
        t = ts.astimezone(BRT)
        if not self.eh_dia_util(t.date()):
            return False
        inicio, fim = self.limites(t.date())
        return inicio <= t < fim

    def duracao_minutos(self) -> int:
        inicio = datetime.combine(date(2000, 1, 3), self.abertura, tzinfo=BRT)
        fim = datetime.combine(date(2000, 1, 3), self.fechamento, tzinfo=BRT)
        return int((fim - inicio).total_seconds() // 60)

    def sessao_de(self, ts: datetime) -> Optional[tuple[datetime, datetime]]:
        """Limites da sessao a que o instante pertence, ou None se fora dela."""
        t = ts.astimezone(BRT)
        if not self.eh_dia_util(t.date()):
            return None
        inicio, fim = self.limites(t.date())
        return (inicio, fim) if inicio <= t < fim else None

    def proximo_dia_util(self, dia: date) -> date:
        d = dia + timedelta(days=1)
        while not self.eh_dia_util(d):
            d += timedelta(days=1)
        return d


SESSAO_B3 = Sessao()
"""Pregao regular de acoes da B3 (10:00 as 17:55, horario de Brasilia)."""

SESSAO_B3_COM_LEILAO = Sessao(fechamento=time(18, 0), nome="B3 - acoes + leilao de fechamento")
"""Inclui o leilao de fechamento (ate as 18:00)."""

SESSAO_WIN = Sessao(abertura=time(9, 0), fechamento=time(18, 25), nome="B3 - indice futuro")
"""Mini indice / mini dolar, que abrem antes das acoes."""
