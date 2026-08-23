"""Modelos da boleta: tipo, campos e o conjunto gerado por oportunidade."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence

from ...models import Direction, formata_dinheiro
from .regras import Regra, regra


class TipoBoleta(str, Enum):
    """Os quatro tipos da boleta."""

    COMPRA = "Compra"
    COMPRA_STOP = "Compra Stop"
    VENDA = "Venda"
    VENDA_STOP = "Venda Stop"

    @property
    def eh_stop(self) -> bool:
        return self in (TipoBoleta.COMPRA_STOP, TipoBoleta.VENDA_STOP)

    @property
    def eh_compra(self) -> bool:
        return self in (TipoBoleta.COMPRA, TipoBoleta.COMPRA_STOP)

    @property
    def direcao(self) -> Direction:
        return Direction.LONG if self.eh_compra else Direction.SHORT


class PapelDaBoleta(str, Enum):
    """Para que serve cada boleta do conjunto."""

    ENTRADA = "entrada"
    STOP = "stop (protecao)"
    ALVO = "alvo (realizacao)"
    OCO = "OCO (gain e loss)"


@dataclass(frozen=True)
class CampoBoleta:
    """Um campo da boleta, pronto para copiar.

    ``confirmado`` diz se o COMPORTAMENTO do campo na Genial foi verificado -
    nao se o valor esta certo. O valor e' calculado pelo Cashinho; o que pode
    estar errado e' a suposicao sobre como a plataforma usa aquele campo.
    """

    rotulo: str
    valor: str
    valor_bruto: Optional[float] = None
    confirmado: bool = True
    observacao: str = ""
    regra_chave: str = ""

    @property
    def regra(self) -> Optional[Regra]:
        return regra(self.regra_chave) if self.regra_chave else None

    @property
    def selo(self) -> str:
        return "" if self.confirmado else "REGRA GENIAL A CONFIRMAR"

    def para_dict(self) -> dict:
        return {
            "rotulo": self.rotulo,
            "valor": self.valor,
            "valor_bruto": self.valor_bruto,
            "confirmado": self.confirmado,
            "observacao": self.observacao,
        }


@dataclass(frozen=True)
class Boleta:
    """Uma boleta pronta para ser digitada na plataforma."""

    tipo: TipoBoleta
    papel: PapelDaBoleta
    campos: tuple[CampoBoleta, ...]
    explicacao: str = ""

    def campo(self, rotulo: str) -> Optional[CampoBoleta]:
        alvo = rotulo.strip().lower()
        for c in self.campos:
            if c.rotulo.strip().lower() == alvo:
                return c
        return None

    def valor(self, rotulo: str) -> Optional[str]:
        c = self.campo(rotulo)
        return c.valor if c else None

    @property
    def pendencias(self) -> tuple[CampoBoleta, ...]:
        return tuple(c for c in self.campos if not c.confirmado)

    def para_copiar(self) -> str:
        """So os campos, alinhados - feito para copiar e digitar."""
        largura = max((len(c.rotulo) for c in self.campos), default=0)
        return "\n".join(f"{c.rotulo:<{largura}}  {c.valor}" for c in self.campos)

    def para_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "papel": self.papel.value,
            "explicacao": self.explicacao,
            "campos": [c.para_dict() for c in self.campos],
        }


@dataclass(frozen=True)
class ResumoOperacao:
    """Os numeros da operacao que acompanham a boleta."""

    ativo: str
    entrada: float
    stop: float
    alvo: float
    quantidade: int
    risco_monetario: float
    retorno_potencial: float
    rr: float
    score: float
    setup: str
    status: str
    timestamp: datetime
    direcao: Optional[Direction] = None

    def para_dict(self) -> dict:
        return {
            "ativo": self.ativo,
            "direcao": self.direcao.value if self.direcao else None,
            "entrada": round(self.entrada, 4),
            "stop": round(self.stop, 4),
            "alvo": round(self.alvo, 4),
            "quantidade": self.quantidade,
            "risco_monetario": round(self.risco_monetario, 2),
            "retorno_potencial": round(self.retorno_potencial, 2),
            "rr": round(self.rr, 2),
            "score": round(self.score, 1),
            "setup": self.setup,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class Ticket:
    """O conjunto gerado para uma oportunidade.

    Nao envia nada: e' um roteiro de digitacao. ``gerado`` fica ``False``
    quando a oportunidade nao esta aprovada - e ``motivo`` diz por que.
    """

    gerado: bool
    motivo: str = ""
    resumo: Optional[ResumoOperacao] = None
    boletas: tuple[Boleta, ...] = ()
    entrar_somente_se: tuple[str, ...] = ()
    cancelar_se: tuple[str, ...] = ()
    pendencias: tuple[Regra, ...] = ()
    avisos: tuple[str, ...] = ()

    def boleta(self, papel: PapelDaBoleta) -> Optional[Boleta]:
        for b in self.boletas:
            if b.papel is papel:
                return b
        return None

    @property
    def entrada(self) -> Optional[Boleta]:
        return self.boleta(PapelDaBoleta.ENTRADA)

    def para_dict(self) -> dict:
        return {
            "gerado": self.gerado,
            "motivo": self.motivo,
            "resumo": self.resumo.para_dict() if self.resumo else None,
            "boletas": [b.para_dict() for b in self.boletas],
            "entrar_somente_se": list(self.entrar_somente_se),
            "cancelar_se": list(self.cancelar_se),
            "pendencias": [r.para_dict() for r in self.pendencias],
            "avisos": list(self.avisos),
            "envia_ordem": False,
        }
