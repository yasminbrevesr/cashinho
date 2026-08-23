"""O cofre do TEST: o conjunto que a otimizacao nao pode tocar.

A regra tem uma razao pratica: cada vez que voce olha o TEST e muda alguma
coisa por causa do que viu, ele deixa de ser out-of-sample e vira mais um
conjunto de treino - so que disfarcado. O resultado final passa a ser
otimista, e voce so descobre operando dinheiro de verdade.

Por isso o TEST nao fica solto num atributo: fica atras de um cofre que
**exige um motivo para abrir** e **conta quantas vezes foi aberto**. Uma
segunda abertura nao e' bloqueada - as vezes ela e' legitima -, mas aparece
no relatorio, em destaque, para ninguem se enganar depois.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...models import BRT, Series
from .divisao import Janela, Particao


class TesteProtegidoError(RuntimeError):
    """Tentativa de usar o TEST onde ele nao pode entrar."""


@dataclass(frozen=True)
class Abertura:
    """O registro de uma consulta ao TEST."""

    motivo: str
    quando: datetime

    def para_dict(self) -> dict:
        return {"motivo": self.motivo, "quando": self.quando.isoformat()}


class CofreDeTeste:
    """Guarda a janela de teste e registra cada abertura."""

    def __init__(self, janela: Janela, relogio=None):
        if janela.particao is not Particao.TEST:
            raise TesteProtegidoError(
                f"o cofre guarda apenas a particao TEST (recebeu {janela.particao.rotulo})"
            )
        self._janela = janela
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self._aberturas: list[Abertura] = []

    # -- o que da para saber sem abrir -----------------------------------
    @property
    def periodo(self) -> tuple:
        """Inicio e fim - metadado, nao preco."""
        return (self._janela.inicio, self._janela.fim)

    @property
    def dias(self) -> int:
        return self._janela.dias

    @property
    def candles(self) -> int:
        return self._janela.candles

    @property
    def aberturas(self) -> tuple[Abertura, ...]:
        return tuple(self._aberturas)

    @property
    def vezes(self) -> int:
        return len(self._aberturas)

    @property
    def foi_aberto(self) -> bool:
        return bool(self._aberturas)

    @property
    def contaminado(self) -> bool:
        """Aberto mais de uma vez - deixou de ser um teste limpo."""
        return self.vezes > 1

    # -- abrir --------------------------------------------------------------
    def abrir(self, motivo: str) -> Janela:
        """Entrega a janela de teste. Exige motivo, e fica registrado."""
        if not motivo or not motivo.strip():
            raise TesteProtegidoError(
                "abrir o cofre do TEST exige um motivo - e' o que fica no relatorio"
            )
        self._aberturas.append(Abertura(motivo.strip(), self._relogio()))
        return self._janela

    def espiar_metadados(self) -> dict:
        """Periodo e tamanho, sem tocar nos precos - nao conta como abertura."""
        return {
            "inicio": self._janela.inicio.isoformat(),
            "fim": self._janela.fim.isoformat(),
            "dias": self.dias,
            "candles": self.candles,
        }

    def para_dict(self) -> dict:
        return {
            **self.espiar_metadados(),
            "vezes_aberto": self.vezes,
            "contaminado": self.contaminado,
            "aberturas": [a.para_dict() for a in self._aberturas],
        }

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        estado = "aberto" if self.foi_aberto else "fechado"
        return f"<CofreDeTeste {self._janela.inicio}..{self._janela.fim} {estado} ({self.vezes}x)>"


def garantir_sem_teste(particoes) -> None:
    """Barreira usada pela otimizacao: TEST nao entra aqui.

    Chamada no comeco de qualquer rotina que avalie parametros. E' a diferenca
    entre "combinamos de nao usar o teste" e "nao da para usar o teste".
    """
    for p in particoes:
        alvo = getattr(p, "particao", p)
        if alvo is Particao.TEST:
            raise TesteProtegidoError(
                "otimizacao nao avalia parametros sobre o TEST: ele existe para medir "
                "uma vez, no fim. Use TRAIN para ajustar e VALIDATION para escolher"
            )
