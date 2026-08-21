"""Porta de tempo.

Decisao arquitetural D3: e proibido chamar `datetime.now()` dentro de
`cashinho/`. Toda leitura de tempo passa por um `Clock`.

Sem esta porta, Market Replay e os testes anti-look-ahead virariam
reescrita do nucleo mais adiante.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Fonte do instante logico do sistema.

    Implementacoes devem retornar sempre datetime timezone-aware em UTC.
    """

    @property
    def kind(self) -> str:
        """Identificador da implementacao, registrado no AnalysisRun."""
        ...

    def now(self) -> datetime:
        """Instante logico atual, em UTC."""
        ...
