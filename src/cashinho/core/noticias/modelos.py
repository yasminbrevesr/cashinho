"""O evento estruturado e a agenda que o guarda.

O ``Evento`` carrega exatamente os campos pedidos - ``event_type``, ``symbol``,
``timestamp``, ``severity``, ``directional_bias``, ``confidence``, ``source`` -
e nada que se pareca com uma ordem. Nao ha preco de entrada aqui, nao ha
direcao de operacao, e ``directional_bias`` e' informacao sobre a notícia, nao
instrucao sobre o book.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

from .tipos import Disponibilidade, Severidade, TipoDeEvento, ViesDirecional


class EventoInvalidoError(ValueError):
    """Registro que nao vira evento - e nao e' consertado por adivinhacao."""


@dataclass(frozen=True)
class Evento:
    """Um evento de mercado, como dado estruturado."""

    event_type: TipoDeEvento
    symbol: str            # vazio = mercado inteiro (juros, inflacao, payroll)
    timestamp: datetime    # quando o evento acontece/aconteceu
    severity: Severidade
    directional_bias: ViesDirecional
    confidence: float      # 0..1 - quanta certeza a fonte tem do registro
    source: str            # de onde veio, por nome

    titulo: str = ""
    detalhe: str = ""
    confirmado: bool = True   # False = data provavel, ainda nao confirmada
    recebido_em: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise EventoInvalidoError(
                f"confidence precisa ficar entre 0 e 1 (recebido: {self.confidence})")
        if not self.source or not self.source.strip():
            raise EventoInvalidoError(
                "todo evento precisa dizer de onde veio: sem source nao ha como "
                "julgar se da para confiar")
        if self.event_type.macro and self.symbol:
            object.__setattr__(self, "symbol", self.symbol.upper())
        elif self.symbol:
            object.__setattr__(self, "symbol", self.symbol.upper())

    # -- consultas -------------------------------------------------------
    @property
    def mercado_inteiro(self) -> bool:
        return not self.symbol

    @property
    def alvo(self) -> str:
        return self.symbol or "MERCADO"

    def atinge(self, symbol: str) -> bool:
        """Evento macro atinge todo mundo; evento de ativo, so o ativo."""
        if self.mercado_inteiro:
            return True
        return bool(symbol) and symbol.upper() == self.symbol

    def minutos_ate(self, instante: datetime) -> float:
        """Positivo = ainda vai acontecer; negativo = ja aconteceu."""
        return (self.timestamp - instante).total_seconds() / 60

    def contraria(self, direcao) -> bool:
        """A notícia empurra para o lado contrario ao da operacao?

        Nao existe o espelho disso: nenhum metodo aqui diz que a notícia
        "confirma" uma operacao. Este modulo so sabe apontar risco.
        """
        if not self.directional_bias.conhecido or direcao is None:
            return False
        nome = getattr(direcao, "value", str(direcao)).lower()
        if self.directional_bias is ViesDirecional.ALTA:
            return nome in ("short", "sell", "venda")
        return nome in ("long", "buy", "compra")

    def para_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "directional_bias": self.directional_bias.value,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "titulo": self.titulo,
            "detalhe": self.detalhe,
            "confirmado": self.confirmado,
            "mercado_inteiro": self.mercado_inteiro,
        }


@dataclass(frozen=True)
class AgendaDeEventos:
    """Os eventos conhecidos - e o estado da fonte que os trouxe.

    Uma agenda vazia com fonte DISPONIVEL significa "nao ha evento a vista".
    Uma agenda vazia com fonte INDISPONIVEL significa "nao sabemos" - e as
    duas coisas nao podem ser confundidas na tela nem na decisao.
    """

    eventos: tuple[Evento, ...] = ()
    disponibilidade: Disponibilidade = Disponibilidade.SEM_FONTE
    atualizado_em: Optional[datetime] = None
    fonte: str = ""
    motivo: str = ""
    descartados: tuple[str, ...] = ()  # registros recusados, com o porque

    def __len__(self) -> int:
        return len(self.eventos)

    @property
    def confiavel(self) -> bool:
        return self.disponibilidade.confiavel

    @property
    def rotulo(self) -> str:
        return self.disponibilidade.rotulo

    def idade_em(self, instante: datetime) -> Optional[float]:
        if self.atualizado_em is None:
            return None
        return (instante - self.atualizado_em).total_seconds() / 60

    # -- consultas -------------------------------------------------------
    def para(self, symbol: str) -> tuple[Evento, ...]:
        return tuple(e for e in self.eventos if e.atinge(symbol))

    def na_janela(self, instante: datetime, antes_min: float, depois_min: float,
                  symbol: str = "") -> tuple[Evento, ...]:
        """Eventos que caem entre ``instante - depois`` e ``instante + antes``.

        ``antes_min`` olha para a frente (evento que ainda vai acontecer) e
        ``depois_min`` olha para tras (evento recem-ocorrido).
        """
        achados = []
        for e in self.eventos:
            if symbol and not e.atinge(symbol):
                continue
            faltam = e.minutos_ate(instante)
            if -depois_min <= faltam <= antes_min:
                achados.append(e)
        return tuple(sorted(achados, key=lambda e: abs(e.minutos_ate(instante))))

    def proximos(self, instante: datetime, symbol: str = "",
                 limite: int = 5) -> tuple[Evento, ...]:
        futuros = [e for e in self.eventos
                   if e.minutos_ate(instante) >= 0 and (not symbol or e.atinge(symbol))]
        return tuple(sorted(futuros, key=lambda e: e.timestamp)[:limite])

    def para_dict(self) -> dict:
        return {
            "disponibilidade": self.disponibilidade.value,
            "confiavel": self.confiavel,
            "rotulo": self.rotulo,
            "fonte": self.fonte,
            "atualizado_em": self.atualizado_em.isoformat() if self.atualizado_em else None,
            "motivo": self.motivo,
            "eventos": [e.para_dict() for e in self.eventos],
            "descartados": list(self.descartados),
        }


def agenda_indisponivel(motivo: str, fonte: str = "",
                        estado: Disponibilidade = Disponibilidade.INDISPONIVEL,
                        atualizado_em: Optional[datetime] = None) -> AgendaDeEventos:
    """Agenda sem eventos utilizaveis - com o motivo por escrito."""
    return AgendaDeEventos(eventos=(), disponibilidade=estado, fonte=fonte,
                           motivo=motivo, atualizado_em=atualizado_em)
