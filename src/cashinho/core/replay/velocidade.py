"""Velocidade do replay e o relogio que dita o ritmo."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from ..mtf.timeframes import parse_timeframe


class Velocidade(str, Enum):
    """Quanto mais rapido que o tempo real."""

    X1 = "1x"
    X5 = "5x"
    X10 = "10x"
    X60 = "60x"
    MAXIMA = "maxima"

    @property
    def multiplicador(self) -> float:
        return {
            Velocidade.X1: 1.0,
            Velocidade.X5: 5.0,
            Velocidade.X10: 10.0,
            Velocidade.X60: 60.0,
            Velocidade.MAXIMA: 0.0,  # sem espera
        }[self]

    @property
    def instantanea(self) -> bool:
        return self is Velocidade.MAXIMA

    @classmethod
    def de_texto(cls, texto: str) -> "Velocidade":
        alvo = texto.strip().lower().replace(" ", "")
        for v in cls:
            if v.value == alvo:
                return v
        if alvo in ("max", "maxima", "maxima", "instantanea", "0"):
            return cls.MAXIMA
        if alvo.rstrip("x").isdigit():
            for v in cls:
                if v.multiplicador == float(alvo.rstrip("x")):
                    return v
        raise ValueError(
            f"velocidade invalida: {texto!r} (use {', '.join(v.value for v in cls)})"
        )


@dataclass
class Relogio:
    """Traduz a velocidade em espera entre candles.

    ``dormir`` e' injetavel para o teste nao precisar esperar de verdade -
    e para quem quiser plugar outro mecanismo de espera.
    """

    velocidade: Velocidade = Velocidade.MAXIMA
    dormir: Callable[[float], None] = time.sleep
    esperas: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.esperas is None:
            self.esperas = []

    def intervalo(self, timeframe: str) -> float:
        """Segundos de espera entre dois candles daquele timeframe."""
        if self.velocidade.instantanea:
            return 0.0
        minutos = parse_timeframe(timeframe).minutos or 1
        return minutos * 60.0 / self.velocidade.multiplicador

    def esperar(self, timeframe: str) -> float:
        segundos = self.intervalo(timeframe)
        self.esperas.append(segundos)
        if segundos > 0:
            self.dormir(segundos)
        return segundos
