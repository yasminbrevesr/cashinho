"""Modelos do Contrarian Auditor.

O auditor trabalha ao contrario do resto do sistema: enquanto a estrategia e o
score procuram razoes para operar, ele procura razoes para NAO operar. Por
isso cada checagem e' escrita como uma tentativa de invalidacao - e o que ela
devolve quando falha ("nao consegui invalidar") vira um fator favoravel, com
o numero que sustenta a afirmacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severidade(str, Enum):
    """O peso de um achado."""

    CRITICO = "critico"  # impede a aprovacao, ponto final
    ALERTA = "alerta"  # desconta score e entra nos avisos
    OBSERVACAO = "observacao"  # so informa

    @property
    def bloqueia(self) -> bool:
        return self is Severidade.CRITICO

    @property
    def simbolo(self) -> str:
        return {"critico": "✖", "alerta": "!", "observacao": "·"}[self.value]


@dataclass(frozen=True)
class Checagem:
    """Uma tentativa de invalidacao, com o resultado e a evidencia."""

    chave: str
    titulo: str
    passou: bool  # True = o auditor NAO conseguiu invalidar por aqui
    detalhe: str
    severidade: Optional[Severidade] = None  # so quando nao passou
    ajuste: float = 0.0  # desconto no score (negativo)
    verificada: bool = True  # False quando faltou dado para checar
    evidencia: dict = field(default_factory=dict)

    @property
    def critica(self) -> bool:
        return self.severidade is Severidade.CRITICO and not self.passou

    @property
    def alerta(self) -> bool:
        return self.severidade is Severidade.ALERTA and not self.passou

    @property
    def simbolo(self) -> str:
        if not self.verificada:
            return "?"
        if self.passou:
            return "✔"
        return self.severidade.simbolo if self.severidade else "!"

    def para_dict(self) -> dict:
        return {
            "chave": self.chave,
            "titulo": self.titulo,
            "passou": self.passou,
            "verificada": self.verificada,
            "detalhe": self.detalhe,
            "severidade": self.severidade.value if self.severidade else None,
            "ajuste": round(self.ajuste, 2),
        }


@dataclass(frozen=True)
class AuditResult:
    """O veredito do auditor.

    ``approved`` e' o unico campo que decide: uma rejeicao critica o derruba,
    por mais alto que esteja o score.
    """

    approved: bool
    warnings: tuple[str, ...]
    critical_rejections: tuple[str, ...]
    score_adjustment: float
    reasons: tuple[str, ...]

    # detalhamento
    checagens: tuple[Checagem, ...] = ()
    score_original: float = 0.0
    score_final: float = 0.0
    motivo: str = ""

    @property
    def favoraveis(self) -> tuple[Checagem, ...]:
        """As frentes em que o auditor tentou invalidar e nao conseguiu."""
        return tuple(c for c in self.checagens if c.passou and c.verificada)

    @property
    def contrarios(self) -> tuple[Checagem, ...]:
        return tuple(c for c in self.checagens if not c.passou and c.alerta)

    @property
    def criticos(self) -> tuple[Checagem, ...]:
        return tuple(c for c in self.checagens if c.critica)

    @property
    def nao_verificadas(self) -> tuple[Checagem, ...]:
        return tuple(c for c in self.checagens if not c.verificada)

    @property
    def tem_rejeicao_critica(self) -> bool:
        return bool(self.critical_rejections)

    def para_dict(self) -> dict:
        return {
            "approved": self.approved,
            "warnings": list(self.warnings),
            "critical_rejections": list(self.critical_rejections),
            "score_adjustment": round(self.score_adjustment, 2),
            "reasons": list(self.reasons),
            "score_original": round(self.score_original, 1),
            "score_final": round(self.score_final, 1),
            "motivo": self.motivo,
            "checagens": [c.para_dict() for c in self.checagens],
        }
