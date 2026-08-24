"""O pregao nao e' uniforme - e a recomendacao nao pode fingir que e'.

A abertura tem volatilidade e ruido que o meio do dia nao tem; o fechamento
tem volume que a tarde nao tem. Um timeframe otimo as 10h05 pode ser pessimo
as 14h30.

Este arquivo nao aprende nada ainda: ele so **nomeia** os periodos e deixa a
recomendacao carimbada com o periodo em que foi feita. E' o que impede o
sistema de virar "o melhor timeframe do dia", que e' a pergunta errada.
"""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from typing import Optional


class PeriodoDoPregao(str, Enum):
    ABERTURA = "abertura"
    MEIO = "meio"
    TARDE = "tarde"
    FECHAMENTO = "fechamento"
    FORA = "fora do pregao"

    @property
    def rotulo(self) -> str:
        return {
            "abertura": "ABERTURA", "meio": "MEIO DO PREGAO",
            "tarde": "TARDE", "fechamento": "FECHAMENTO",
            "fora do pregao": "FORA DO PREGAO",
        }[self.value]

    @property
    def descricao(self) -> str:
        return {
            "abertura": "primeira hora: volatilidade e ruido altos",
            "meio": "meio da manha ate o almoco",
            "tarde": "tarde, antes do movimento de fechamento",
            "fechamento": "ultima hora: volume e ajuste de posicao",
            "fora do pregao": "mercado fechado",
        }[self.value]

    @property
    def opera(self) -> bool:
        return self is not PeriodoDoPregao.FORA


# limites em horario de Brasilia. Sao pontos de corte declarados, nao
# descobertos: quando houver estatistica por periodo, eles viram configuracao
ABERTURA_ATE = time(11, 0)
MEIO_ATE = time(14, 0)
TARDE_ATE = time(16, 30)


def periodo_de(instante: datetime, sessao=None) -> PeriodoDoPregao:
    """Em que parte do pregao este instante cai."""
    from ..mtf.session import Sessao

    sessao = sessao or Sessao()
    if not sessao.contem(instante):
        return PeriodoDoPregao.FORA

    hora = instante.timetz().replace(tzinfo=None)
    if hora < ABERTURA_ATE:
        return PeriodoDoPregao.ABERTURA
    if hora < MEIO_ATE:
        return PeriodoDoPregao.MEIO
    if hora < TARDE_ATE:
        return PeriodoDoPregao.TARDE
    return PeriodoDoPregao.FECHAMENTO
