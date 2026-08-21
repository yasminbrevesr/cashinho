"""A interface que toda estrategia implementa - e o registro de estrategias.

Isto e' o que a primeira estrategia existe para validar: se um segundo
algoritmo, com regras completamente diferentes, cabe aqui sem que nada em
volta (motor multi-timeframe, estrutura, risco, telas) precise mudar, a
arquitetura esta de pe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable, Optional

from .context import StrategyContext
from .models import Action, Factor, Signal


class Strategy(ABC):
    """Contrato minimo: recebe contexto, devolve :class:`Signal`.

    Regras da casa, valendo para qualquer estrategia:

    - nao envia ordem e nao chama o Risk Manager;
    - nao le candle que ainda nao fechou (o contexto ja chega limpo);
    - sempre devolve um Signal, inclusive ``Action.NONE`` - silencio nao e'
      resposta.
    """

    nome: str = "estrategia"
    descricao: str = ""
    timeframe_preferido: str = "5m"
    experimental: bool = True
    aviso: str = ""

    @abstractmethod
    def avaliar(self, contexto: StrategyContext) -> Signal:
        """Le o contexto e descreve a condicao encontrada."""

    # -- utilitarios para as implementacoes ------------------------------
    def sinal_vazio(
        self,
        contexto: StrategyContext,
        motivo: str,
        factors: Iterable[Factor] = (),
    ) -> Signal:
        """Atalho para ``Action.NONE`` com o motivo registrado."""
        return Signal(
            symbol=contexto.symbol,
            timestamp=contexto.timestamp,
            timeframe=contexto.timeframe,
            action=Action.NONE,
            setup=self.nome,
            confidence=0.0,
            reasons=(motivo,),
            invalidation="-",
            strategy=self.nome,
            factors=tuple(factors),
            experimental=self.experimental,
            aviso=self.aviso,
        )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        return f"<{type(self).__name__} {self.nome}>"


_REGISTRO: dict[str, Callable[[], Strategy]] = {}


def registrar(nome: str, fabrica: Callable[[], Strategy]) -> None:
    """Registra uma estrategia pelo nome, para a interface poder lista-la."""
    chave = nome.strip().lower()
    if chave in _REGISTRO:
        raise ValueError(f"ja existe estrategia registrada como {chave!r}")
    _REGISTRO[chave] = fabrica


def obter(nome: str) -> Strategy:
    chave = nome.strip().lower()
    if chave not in _REGISTRO:
        disponiveis = ", ".join(sorted(_REGISTRO)) or "nenhuma"
        raise KeyError(f"estrategia {nome!r} nao registrada (disponiveis: {disponiveis})")
    return _REGISTRO[chave]()


def disponiveis() -> list[str]:
    return sorted(_REGISTRO)


def limpar_registro() -> None:  # pragma: no cover - usado em teste
    _REGISTRO.clear()
