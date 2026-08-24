"""A saida do Advisor: recomendacao estruturada e explicavel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence

from .amostra import Confianca, Estatistica
from .medidas import MedidasDoTimeframe
from .periodos import PeriodoDoPregao
from .score import ScoreDoTimeframe


class StatusAdvisor(str, Enum):
    """O que o Advisor conseguiu concluir."""

    RECOMENDADO = "RECOMMENDED"
    MANTER_ATUAL = "KEEP_CURRENT"
    CONFIANCA_BAIXA = "LOW_CONFIDENCE"
    DADOS_INSUFICIENTES = "INSUFFICIENT_DATA"

    @property
    def rotulo(self) -> str:
        return {
            "RECOMMENDED": "RECOMENDADO",
            "KEEP_CURRENT": "MANTER O ATUAL",
            "LOW_CONFIDENCE": "SEM RECOMENDACAO CONFIAVEL",
            "INSUFFICIENT_DATA": "DADOS INSUFICIENTES",
        }[self.value]

    @property
    def acionavel(self) -> bool:
        """So RECOMENDADO e MANTER_ATUAL apontam um timeframe para usar."""
        return self in (StatusAdvisor.RECOMENDADO, StatusAdvisor.MANTER_ATUAL)

    @property
    def descricao(self) -> str:
        return {
            "RECOMMENDED": "ha um timeframe claramente melhor agora",
            "KEEP_CURRENT": "o atual segue adequado - trocar seria ruido",
            "LOW_CONFIDENCE": "ha um lider, mas sem sustentacao para afirmar",
            "INSUFFICIENT_DATA": "dados insuficientes para avaliar",
        }[self.value]


@dataclass(frozen=True)
class ItemDoRanking:
    """Um timeframe avaliado, com tudo o que sustenta a nota."""

    timeframe: str
    score: ScoreDoTimeframe
    medidas: MedidasDoTimeframe
    confianca: Confianca
    estatistica: Optional[Estatistica] = None

    @property
    def total(self) -> float:
        return self.score.total

    @property
    def market_fit(self) -> float:
        return self.score.market_fit

    @property
    def statistical_evidence(self) -> Optional[float]:
        return self.score.statistical_evidence

    def para_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "score": self.total,
            "market_fit": self.market_fit,
            "statistical_evidence": self.statistical_evidence,
            "confidence": self.confianca.valor,
            "detalhe": self.score.para_dict(),
            "medidas": self.medidas.para_dict(),
            "estatistica": self.estatistica.para_dict() if self.estatistica else None,
        }


@dataclass(frozen=True)
class TimeframeRecommendation:
    """A recomendacao completa - contexto, setup e gatilho, com o porque."""

    symbol: str
    as_of: datetime
    status: StatusAdvisor

    context_timeframe: Optional[str] = None
    setup_timeframe: Optional[str] = None
    trigger_timeframe: Optional[str] = None

    market_fit_score: float = 0.0
    statistical_evidence_score: Optional[float] = None
    confidence_score: float = 0.0
    confianca: Optional[Confianca] = None

    rankings: tuple[ItemDoRanking, ...] = ()
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    periodo: PeriodoDoPregao = PeriodoDoPregao.FORA
    regime: Optional[str] = None
    decisao: Optional[object] = None       # a decisao de histerese, quando houve

    # ------------------------------------------------------------------
    @property
    def tem_recomendacao(self) -> bool:
        return self.status.acionavel and self.setup_timeframe is not None

    @property
    def lider(self) -> Optional[ItemDoRanking]:
        return self.rankings[0] if self.rankings else None

    def item(self, timeframe: str) -> Optional[ItemDoRanking]:
        for r in self.rankings:
            if r.timeframe == timeframe:
                return r
        return None

    @property
    def resumo(self) -> str:
        if not self.tem_recomendacao:
            return f"{self.status.rotulo}: {self.status.descricao}"
        return (f"contexto {self.context_timeframe} · setup {self.setup_timeframe} "
                f"· gatilho {self.trigger_timeframe}")

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "status": self.status.value,
            "context_timeframe": self.context_timeframe,
            "setup_timeframe": self.setup_timeframe,
            "trigger_timeframe": self.trigger_timeframe,
            "market_fit_score": round(self.market_fit_score, 1),
            "statistical_evidence_score": (
                None if self.statistical_evidence_score is None
                else round(self.statistical_evidence_score, 1)),
            "confidence_score": round(self.confidence_score, 1),
            "confianca": self.confianca.para_dict() if self.confianca else None,
            "rankings": [r.para_dict() for r in self.rankings],
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "periodo": self.periodo.value,
            "regime": self.regime,
            "decisao": (self.decisao.para_dict()
                        if self.decisao is not None and hasattr(self.decisao, "para_dict")
                        else None),
        }
