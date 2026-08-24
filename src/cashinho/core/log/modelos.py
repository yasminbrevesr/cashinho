"""O registro de log - uma linha JSONL, um evento."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional

from ...models import BRT
from .niveis import Nivel, nivel_de


@dataclass(frozen=True)
class EventoDeLog:
    """O que aconteceu, quando, em qual componente - e os dados junto.

    ``dados`` existe para o log ser **consultavel**, nao so legivel: gravar
    "ordem rejeitada: saldo insuficiente" e' texto; gravar junto
    ``{"symbol": "PETR4", "necessario": 3000.9}`` permite responder depois
    "quantas vezes o saldo barrou PETR4 este mes".
    """

    ts: datetime
    nivel: Nivel
    componente: str
    mensagem: str
    dados: Mapping[str, Any] = field(default_factory=dict)

    def para_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(),
            "nivel": self.nivel.value,
            "componente": self.componente,
            "mensagem": self.mensagem,
            **({"dados": dict(self.dados)} if self.dados else {}),
        }

    def para_linha(self) -> str:
        return json.dumps(self.para_dict(), ensure_ascii=False, default=str)

    @classmethod
    def de_dict(cls, bruto: Mapping[str, Any]) -> "EventoDeLog":
        ts = bruto["ts"]
        quando = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=BRT)
        return cls(
            ts=quando,
            nivel=nivel_de(bruto["nivel"]),
            componente=str(bruto.get("componente", "")),
            mensagem=str(bruto.get("mensagem", "")),
            dados=dict(bruto.get("dados") or {}),
        )

    def __str__(self) -> str:
        alvo = f"[{self.componente}] " if self.componente else ""
        return f"{self.ts:%H:%M:%S} {self.nivel.simbolo} {alvo}{self.mensagem}"
