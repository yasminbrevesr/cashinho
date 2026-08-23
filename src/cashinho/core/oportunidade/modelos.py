"""A Opportunity completa - com score, niveis, prazo e estado."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...models import Direction
from ..confluencia.modelos import LeituraMultiTimeframe
from .estados import EstadoOportunidade
from .score import ScoreDetalhado


@dataclass(frozen=True)
class Opportunity:
    """Uma oportunidade avaliada, pontuada e com prazo de validade.

    Nao e' ordem: nao tem quantidade. ``entry``, ``stop`` e ``target`` sao
    referencias para o Risk Manager dimensionar - e ele continua podendo
    dizer nao.
    """

    symbol: str
    timestamp: datetime
    direction: Optional[Direction]
    setup: str
    score: float  # 0..100
    entry: float
    stop: float
    target: float
    risk_reward: float
    timeframe_context: str
    timeframe_trend: str
    timeframe_setup: str
    timeframe_trigger: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    invalidation: str
    expires_at: Optional[datetime]

    # o detalhamento que impede o score de ser caixa-preta
    estado: EstadoOportunidade = EstadoOportunidade.NAO_OPERAR
    score_detalhado: Optional[ScoreDetalhado] = None
    leitura: Optional[LeituraMultiTimeframe] = None
    regra: str = ""
    motivo_do_estado: str = ""
    # leitura da agenda de noticias e eventos, quando o motor tem um avaliador.
    # Fica como Optional[object] para o modulo de oportunidade nao depender do
    # de noticias: a agenda e' um insumo opcional, nao parte do contrato
    eventos: Optional[object] = None

    # ------------------------------------------------------------------
    def expirada_em(self, agora: datetime) -> bool:
        return self.expires_at is not None and agora > self.expires_at

    def estado_em(self, agora: datetime) -> EstadoOportunidade:
        """O estado considerando a passagem do tempo."""
        if self.estado.vale_acompanhar and self.expirada_em(agora):
            return EstadoOportunidade.EXPIRADO
        return self.estado

    @property
    def acionavel(self) -> bool:
        return self.estado.acionavel

    @property
    def risco_por_acao(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def timeframes(self) -> dict[str, str]:
        return {
            "context": self.timeframe_context,
            "trend": self.timeframe_trend,
            "setup": self.timeframe_setup,
            "trigger": self.timeframe_trigger,
        }

    def validade_minutos(self) -> Optional[float]:
        if self.expires_at is None:
            return None
        return (self.expires_at - self.timestamp).total_seconds() / 60.0

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value if self.direction else None,
            "setup": self.setup,
            "score": round(self.score, 1),
            "entry": round(self.entry, 4),
            "stop": round(self.stop, 4),
            "target": round(self.target, 4),
            "risk_reward": round(self.risk_reward, 3),
            "timeframe_context": self.timeframe_context,
            "timeframe_trend": self.timeframe_trend,
            "timeframe_setup": self.timeframe_setup,
            "timeframe_trigger": self.timeframe_trigger,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "invalidation": self.invalidation,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "estado": self.estado.value,
            "motivo_do_estado": self.motivo_do_estado,
            "eventos": self.eventos.para_dict() if self.eventos is not None else None,
            "regra": self.regra,
            "score_detalhado": self.score_detalhado.para_dict() if self.score_detalhado else None,
        }
