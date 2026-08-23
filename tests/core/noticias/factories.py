"""Eventos e agendas para os testes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.noticias import (
    AgendaDeEventos,
    Disponibilidade,
    Evento,
    FonteEmMemoria,
    Severidade,
    TipoDeEvento,
    ViesDirecional,
)
from cashinho.models import BRT

AGORA = datetime(2026, 8, 21, 11, 0, tzinfo=BRT)


def evento(tipo: TipoDeEvento = TipoDeEvento.RESULTADOS, symbol: str = "PETR4",
           minutos: float = 30, severidade: Severidade = Severidade.ALTA,
           vies: ViesDirecional = ViesDirecional.INDEFINIDO, confianca: float = 0.9,
           fonte: str = "calendario manual", instante: datetime = AGORA,
           **campos) -> Evento:
    return Evento(
        event_type=tipo, symbol=symbol, timestamp=instante + timedelta(minutes=minutos),
        severity=severidade, directional_bias=vies, confidence=confianca,
        source=fonte, **campos,
    )


def agenda(eventos: Sequence[Evento] = (), instante: datetime = AGORA,
           disponibilidade: Disponibilidade = Disponibilidade.DISPONIVEL) -> AgendaDeEventos:
    return FonteEmMemoria(eventos, instante, disponibilidade).carregar(instante)


def arquivo_de_eventos(pasta, eventos: Sequence[dict] = (),
                       atualizado_em: Optional[datetime] = AGORA,
                       fonte: str = "calendario manual", **extra) -> str:
    dados = {"fonte": fonte, "eventos": list(eventos), **extra}
    if atualizado_em is not None:
        dados["atualizado_em"] = atualizado_em.isoformat()
    caminho = pasta / "eventos.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return str(caminho)


def bruto(tipo: str = "resultados", symbol: str = "PETR4", minutos: float = 30,
          severidade: str = "alta", instante: datetime = AGORA, **campos) -> dict:
    registro = {
        "event_type": tipo,
        "symbol": symbol,
        "timestamp": (instante + timedelta(minutes=minutos)).isoformat(),
        "severity": severidade,
        "directional_bias": "indefinido",
        "confidence": 0.9,
        "source": "calendario manual",
    }
    registro.update(campos)
    return registro
