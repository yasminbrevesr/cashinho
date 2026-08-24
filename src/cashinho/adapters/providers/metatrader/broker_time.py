"""Normalizacao do relogio do servidor da corretora.

O ERRO QUE ESTE MODULO EXISTE PARA IMPEDIR
==========================================
O inteiro que o MetaTrader devolve em `time` **nao e** epoch UTC. E o relogio
de parede do servidor da corretora empacotado como se fosse. Tratar aquele
numero com

    datetime.fromtimestamp(bruto, tz=UTC)

desloca o horario: um negocio das 17:05 no terminal da Genial vira 14:05, e o
sistema inteiro passa a acreditar num pregao que nao existiu.

O caminho correto tem tres passos, e o segundo e o que costuma faltar:

    inteiro do MT5
        -> relogio de parede que ele representa      (ingenuo)
        -> esse relogio COM o fuso do servidor        (MT5_SERVER_TIMEZONE)
        -> convertido para UTC                        (regra 2 do projeto)

Toda a logica de fuso do MetaTrader vive aqui. Nem o provider nem a interface
convertem horario por conta propria.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

DEFAULT_SERVER_TIMEZONE = "America/Sao_Paulo"
"""Fuso do servidor da Genial (`GenialInvestimentos-PRD`)."""


def resolve_timezone(name: str) -> tzinfo:
    """Resolve o nome do fuso, com mensagem util quando a base falta.

    No Windows a base de fusos pode nao existir sem o pacote `tzdata`. Falhar
    aqui com instrucao e melhor do que cair num deslocamento silencioso.
    """
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValueError(
            f"fuso '{name}' desconhecido neste sistema. No Windows, instale a "
            "base de fusos com 'pip install tzdata'"
        ) from exc


@dataclass(frozen=True)
class BrokerTimeNormalizer:
    """Traduz o relogio do servidor da corretora para UTC.

    `server_timezone` e o fuso em que o terminal marca as horas. Para a
    Genial, `America/Sao_Paulo`.
    """

    server_timezone: str = DEFAULT_SERVER_TIMEZONE

    @property
    def tz(self) -> tzinfo:
        return resolve_timezone(self.server_timezone)

    # ------------------------------------------------------------------
    def to_utc(self, raw: int | float) -> datetime:
        """O caminho completo: inteiro do MT5 -> UTC aware."""
        wall = self.wall_clock(raw)
        return wall.replace(tzinfo=self.tz).astimezone(UTC)

    def to_utc_msc(self, raw_msc: int | float) -> datetime:
        """Mesma conta para `time_msc`, o campo em milissegundos."""
        return self.to_utc(float(raw_msc) / 1000.0)

    @staticmethod
    def wall_clock(raw: int | float) -> datetime:
        """O relogio que o inteiro representa, **sem fuso**.

        `fromtimestamp(..., tz=utc)` seguido de `replace(tzinfo=None)` nao
        converte nada: apenas desempacota o numero de volta no relogio que o
        servidor mostrou. O fuso correto e colado no passo seguinte.
        """
        return datetime.fromtimestamp(float(raw), tz=UTC).replace(tzinfo=None)

    def from_utc(self, moment: datetime) -> datetime:
        """Caminho de volta: UTC -> relogio ingenuo do servidor.

        E o formato que `copy_ticks_from` e `copy_rates_from` esperam.
        """
        if moment.tzinfo is None:
            raise ValueError(
                "instante sem fuso: o Cashinho nao aceita datetime naive "
                "(regra 2)"
            )
        return moment.astimezone(self.tz).replace(tzinfo=None)

    def server_now(self, utc_now: datetime) -> datetime:
        """O 'agora' do sistema visto pelo relogio do servidor, ingenuo."""
        return self.from_utc(utc_now)
