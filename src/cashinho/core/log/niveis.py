"""Os niveis do log - e o que cada um significa neste projeto.

A escala e' curta de proposito. Cinco niveis que ninguem sabe distinguir viram
cinco niveis usados ao acaso; estes quatro tem criterio:

- ``DEBUG``: rastro para entender uma decisao depois. Desligado por padrao;
- ``INFO``: aconteceu algo que vale estar no historico do pregao - ordem
  enviada, varredura concluida, kill switch liberado;
- ``AVISO``: algo saiu do esperado mas o robo seguiu - agenda desatualizada,
  fonte lenta, divergencia reconciliada;
- ``ERRO``: algo falhou. Alguem precisa olhar.

Nao ha ``CRITICO`` separado: no Cashinho, o que e' critico nao vira nivel de
log, vira **bloqueio** - kill switch, `NAO OPERAR`, `BrokerComSaude`. Um log
mais vermelho nao para operacao nenhuma.
"""

from __future__ import annotations

from enum import Enum


class Nivel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    AVISO = "aviso"
    ERRO = "erro"

    @property
    def peso(self) -> int:
        return {"debug": 0, "info": 1, "aviso": 2, "erro": 3}[self.value]

    @property
    def rotulo(self) -> str:
        return self.value.upper()

    @property
    def simbolo(self) -> str:
        return {"debug": "·", "info": "•", "aviso": "!", "erro": "✖"}[self.value]

    @property
    def cor(self) -> str:
        return {"debug": "cinza", "info": "", "aviso": "amarelo", "erro": "vermelho"}[self.value]

    def __ge__(self, outro) -> bool:  # type: ignore[override]
        if isinstance(outro, Nivel):
            return self.peso >= outro.peso
        return NotImplemented

    def __gt__(self, outro) -> bool:  # type: ignore[override]
        if isinstance(outro, Nivel):
            return self.peso > outro.peso
        return NotImplemented

    def __le__(self, outro) -> bool:  # type: ignore[override]
        if isinstance(outro, Nivel):
            return self.peso <= outro.peso
        return NotImplemented

    def __lt__(self, outro) -> bool:  # type: ignore[override]
        if isinstance(outro, Nivel):
            return self.peso < outro.peso
        return NotImplemented


def nivel_de(valor) -> Nivel:
    """Aceita ``"aviso"`` e ``Nivel.AVISO``.

    A idempotencia nao e' luxo: ``Nivel`` herda de ``str``, entao o argparse
    trata um default ``Nivel.DEBUG`` como string e o converte de novo.
    """
    if isinstance(valor, Nivel):
        return valor
    try:
        return Nivel(str(valor).strip().lower())
    except ValueError:
        raise ValueError(
            f"nivel desconhecido: {valor!r} (use {', '.join(n.value for n in Nivel)})"
        ) from None
