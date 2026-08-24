"""Normalizacao do horario do servidor da Genial.

O ERRO QUE ESTA CLASSE EXISTE PARA IMPEDIR
==========================================
O timestamp que o MT5 devolve **nao e' UTC**. Ele e' o relogio do servidor da
corretora, empacotado como se fosse epoch. Tratar aquele numero com

    datetime.fromtimestamp(bruto, tz=UTC).astimezone(BRT)

joga o horario 3 horas para tras: um negocio das 17:05 do pregao vira 14:05, e
todo o resto do sistema passa a acreditar num pregao que nao existiu.

O caminho certo tem tres passos:

    numero bruto do MT5
        -> relogio de parede (sem fuso) que ele representa
        -> esse relogio COM o fuso do servidor  (MT5_SERVER_TIMEZONE)
        -> convertido para o fuso do dominio

O segundo passo e' o que costuma faltar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional, Union

from ...models import BRT

FUSO_PADRAO_DO_SERVIDOR = "America/Sao_Paulo"


def fuso(nome: str) -> tzinfo:
    """O fuso pelo nome. Usa zoneinfo quando ha base de fusos instalada.

    No Windows a base pode nao existir sem o pacote ``tzdata``; nesse caso o
    horario de Brasilia cai no deslocamento fixo de -3, que e' o valor correto
    desde 2019 (o Brasil nao tem mais horario de verao). Fusos com verao ativo
    exigem a base instalada, e isso esta documentado.
    """
    if not nome or nome == FUSO_PADRAO_DO_SERVIDOR:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(FUSO_PADRAO_DO_SERVIDOR)
        except Exception:
            return BRT
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(nome)
    except Exception as e:
        raise ValueError(
            f"fuso '{nome}' desconhecido neste sistema. No Windows, instale a "
            "base de fusos com 'pip install tzdata', ou use America/Sao_Paulo"
        ) from e


@dataclass(frozen=True)
class NormalizadorDeTempoDoBroker:
    """Traduz o relogio do servidor da corretora para o do dominio.

    ``fuso_do_servidor`` e' o fuso em que o terminal marca as horas - para a
    Genial, ``America/Sao_Paulo``. ``fuso_do_dominio`` e' como o Cashinho
    guarda: sempre com fuso, nunca ingenuo.
    """

    fuso_do_servidor: str = FUSO_PADRAO_DO_SERVIDOR
    fuso_do_dominio: tzinfo = BRT

    @property
    def tz_servidor(self) -> tzinfo:
        return fuso(self.fuso_do_servidor)

    # ------------------------------------------------------------------
    def de_epoch(self, bruto: Union[int, float]) -> datetime:
        """O caminho completo, do numero do MT5 ao horario com fuso."""
        if bruto is None:
            raise ValueError("timestamp do MT5 ausente")
        relogio = self.relogio_de_parede(bruto)
        return relogio.replace(tzinfo=self.tz_servidor).astimezone(self.fuso_do_dominio)

    def de_epoch_ms(self, bruto_ms: Union[int, float]) -> datetime:
        """Mesma conta para o campo em milissegundos (``time_msc``)."""
        return self.de_epoch(float(bruto_ms) / 1000.0)

    @staticmethod
    def relogio_de_parede(bruto: Union[int, float]) -> datetime:
        """O relogio que o numero representa, **sem** fuso nenhum.

        E' aqui que mora a sutileza: ``utcfromtimestamp`` nao esta convertendo
        nada para UTC - esta desempacotando o numero de volta no relogio que o
        servidor mostrou. O fuso certo e' colado no passo seguinte.
        """
        return datetime.fromtimestamp(float(bruto), tz=timezone.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    def para_epoch(self, momento: datetime) -> float:
        """O caminho de volta - para pedir ticks a partir de um instante."""
        if momento.tzinfo is None:
            raise ValueError(
                "instante sem fuso: o Cashinho nao mistura horario ingenuo com "
                "horario com fuso")
        no_servidor = momento.astimezone(self.tz_servidor)
        ingenuo = no_servidor.replace(tzinfo=None)
        return ingenuo.replace(tzinfo=timezone.utc).timestamp()

    def agora_no_servidor(self, agora: Optional[datetime] = None) -> datetime:
        """O 'agora' visto pelo relogio do servidor."""
        instante = agora or datetime.now(self.fuso_do_dominio)
        return instante.astimezone(self.tz_servidor)

    def para_dict(self) -> dict:
        return {"fuso_do_servidor": self.fuso_do_servidor,
                "fuso_do_dominio": str(self.fuso_do_dominio)}
