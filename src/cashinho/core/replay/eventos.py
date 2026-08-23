"""Os eventos que o replay emite - e' o que o grafico desenha."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class TipoEvento(str, Enum):
    SINAL = "sinal"
    ENTRADA = "entrada"
    STOP = "stop"
    ALVO = "alvo"
    SAIDA = "saida"
    BARRADO = "barrado"

    @property
    def marcador(self) -> str:
        return {
            TipoEvento.SINAL: "s",
            TipoEvento.ENTRADA: "E",
            TipoEvento.STOP: "S",
            TipoEvento.ALVO: "A",
            TipoEvento.SAIDA: "X",
            TipoEvento.BARRADO: "·",
        }[self]


@dataclass(frozen=True)
class EventoReplay:
    """Algo que aconteceu num candle - com o indice para o grafico marcar."""

    tipo: TipoEvento
    indice: int  # posicao na fita
    ts: datetime
    preco: float
    descricao: str
    direcao: Optional[Direction] = None
    detalhes: dict = field(default_factory=dict)

    @property
    def marcador(self) -> str:
        return self.tipo.marcador

    def para_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "indice": self.indice,
            "ts": self.ts.isoformat(),
            "preco": round(self.preco, 4),
            "descricao": self.descricao,
            "direcao": self.direcao.value if self.direcao else None,
        }
