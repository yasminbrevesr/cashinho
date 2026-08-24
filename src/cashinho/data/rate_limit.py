"""Freio de requisicoes - para nao bombardear API de terceiro.

Janela deslizante simples: N requisicoes por periodo. Quando o teto e'
atingido, a proxima chamada **espera** o tempo necessario em vez de disparar.
Sem teto configurado, nao ha freio - e isso e' escolha de quem configurou, nao
padrao escondido.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Deque, Optional


class Freio:
    """Limitador de taxa por janela deslizante."""

    def __init__(self, por_minuto: Optional[float] = None,
                 relogio: Optional[Callable[[], float]] = None,
                 dormir: Optional[Callable[[float], None]] = None):
        self.por_minuto = por_minuto
        self._relogio = relogio or time.monotonic
        self._dormir = dormir or time.sleep
        self._chamadas: Deque[float] = deque()
        self.esperas = 0
        self.tempo_esperado = 0.0

    @property
    def ativo(self) -> bool:
        return bool(self.por_minuto and self.por_minuto > 0)

    def aguardar(self) -> float:
        """Segura a chamada se preciso. Devolve quanto tempo esperou."""
        if not self.ativo:
            return 0.0
        agora = self._relogio()
        janela = 60.0
        while self._chamadas and agora - self._chamadas[0] >= janela:
            self._chamadas.popleft()

        if len(self._chamadas) < self.por_minuto:
            self._chamadas.append(agora)
            return 0.0

        espera = janela - (agora - self._chamadas[0])
        if espera > 0:
            self._dormir(espera)
            self.esperas += 1
            self.tempo_esperado += espera
        agora = self._relogio()
        while self._chamadas and agora - self._chamadas[0] >= janela:
            self._chamadas.popleft()
        self._chamadas.append(agora)
        return max(espera, 0.0)

    def para_dict(self) -> dict:
        return {"por_minuto": self.por_minuto, "ativo": self.ativo,
                "esperas": self.esperas, "tempo_esperado_s": round(self.tempo_esperado, 2)}
