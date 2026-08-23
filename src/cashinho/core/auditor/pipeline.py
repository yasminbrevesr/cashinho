"""O fluxo obrigatorio, escrito como codigo.

    Strategy -> Opportunity -> Score -> Auditor -> Risk Manager -> Resultado

Cada etapa registra se passou e por que. Se uma etapa barra, as seguintes nao
rodam - e o resultado diz exatamente onde parou. Nao ha atalho: nao existe
caminho no pipeline que chegue ao Risk Manager sem passar pelo auditor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...models import Direction
from ..oportunidade.engine import OpportunityEngine
from ..oportunidade.estados import EstadoOportunidade
from ..oportunidade.modelos import Opportunity
from ..risk import PedidoOperacao, RiskDecision, RiskManager
from ..strategy.base import Strategy
from ..strategy.context import de_vista
from ..strategy.models import Signal
from .auditor import ContrarianAuditor
from .modelos import AuditResult


@dataclass(frozen=True)
class Etapa:
    """Uma etapa do fluxo, com o veredito dela."""

    ordem: int
    nome: str
    passou: bool
    detalhe: str
    executada: bool = True

    @property
    def simbolo(self) -> str:
        if not self.executada:
            return "·"
        return "✔" if self.passou else "✖"


@dataclass
class ResultadoFinal:
    """O que sai do fluxo inteiro."""

    symbol: str
    instante: datetime
    etapas: list[Etapa] = field(default_factory=list)
    signal: Optional[Signal] = None
    opportunity: Optional[Opportunity] = None
    auditoria: Optional[AuditResult] = None
    decisao_de_risco: Optional[RiskDecision] = None

    @property
    def aprovado(self) -> bool:
        """So e' aprovado quem passou por TODAS as etapas."""
        return bool(
            self.etapas
            and all(e.passou for e in self.etapas if e.executada)
            and len([e for e in self.etapas if e.executada]) == 5
        )

    @property
    def parou_em(self) -> Optional[Etapa]:
        for e in self.etapas:
            if e.executada and not e.passou:
                return e
        return None

    @property
    def resumo(self) -> str:
        if self.aprovado:
            d = self.decisao_de_risco
            return (
                f"aprovado no fluxo completo: {d.position_size} acoes, "
                f"score {self.auditoria.score_final:.0f} apos auditoria"
            )
        parada = self.parou_em
        return f"barrado em {parada.nome}: {parada.detalhe}" if parada else "fluxo nao concluido"

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "instante": self.instante.isoformat(),
            "aprovado": self.aprovado,
            "resumo": self.resumo,
            "etapas": [
                {"ordem": e.ordem, "nome": e.nome, "passou": e.passou,
                 "executada": e.executada, "detalhe": e.detalhe}
                for e in self.etapas
            ],
            "opportunity": self.opportunity.para_dict() if self.opportunity else None,
            "auditoria": self.auditoria.para_dict() if self.auditoria else None,
            "risco": self.decisao_de_risco.para_dict() if self.decisao_de_risco else None,
        }


class Pipeline:
    """Encadeia estrategia, oportunidade, auditor e risco na ordem obrigatoria."""

    ETAPAS = ("Strategy", "Opportunity", "Score", "Auditor", "Risk Manager")

    def __init__(
        self,
        estrategia: Strategy,
        engine: Optional[OpportunityEngine] = None,
        auditor: Optional[ContrarianAuditor] = None,
        risco: Optional[RiskManager] = None,
    ):
        self.estrategia = estrategia
        self.engine = engine or OpportunityEngine()
        self.auditor = auditor or ContrarianAuditor()
        self.risco = risco or RiskManager()

    # ------------------------------------------------------------------
    def executar(self, vista, symbol: str = "", agora: Optional[datetime] = None) -> ResultadoFinal:
        agora = agora or vista.instante
        resultado = ResultadoFinal(symbol=symbol, instante=agora)

        # 1) Strategy ----------------------------------------------------
        sinal = self._rodar_estrategia(vista, symbol)
        resultado.signal = sinal
        if sinal is None:
            resultado.etapas.append(Etapa(1, "Strategy", False, "sem serie fechada para avaliar"))
            return self._pendentes(resultado, 1)
        resultado.etapas.append(
            Etapa(1, "Strategy", sinal.action.acionavel or sinal.action.value == "WAIT",
                  f"{sinal.action.value}: {sinal.setup}")
        )
        if not resultado.etapas[-1].passou:
            return self._pendentes(resultado, 1)

        # 2) Opportunity -------------------------------------------------
        op = self.engine.avaliar(vista, symbol)
        resultado.opportunity = op
        passou = op.estado in (EstadoOportunidade.APROVADO, EstadoOportunidade.AGUARDANDO_GATILHO)
        resultado.etapas.append(Etapa(2, "Opportunity", passou, f"{op.estado.value}: {op.motivo_do_estado}"))
        if not passou:
            return self._pendentes(resultado, 2)

        # 3) Score --------------------------------------------------------
        passou_score = op.estado is EstadoOportunidade.APROVADO
        detalhe = (
            f"score {op.score:.0f}"
            if passou_score
            else f"score {op.score:.0f}, mas o setup ainda nao esta pronto ({op.estado.value})"
        )
        resultado.etapas.append(Etapa(3, "Score", passou_score, detalhe))
        if not passou_score:
            return self._pendentes(resultado, 3)

        # 4) Auditor -------------------------------------------------------
        auditoria = self.auditor.auditar(op, vista, agora)
        resultado.auditoria = auditoria
        resultado.etapas.append(Etapa(4, "Auditor", auditoria.approved, auditoria.motivo))
        if not auditoria.approved:
            return self._pendentes(resultado, 4)

        # 5) Risk Manager ---------------------------------------------------
        decisao = self.risco.avaliar(
            PedidoOperacao(
                symbol=op.symbol,
                direcao=op.direction,
                entrada=op.entry,
                stop=op.stop,
                alvo=op.target,
                referencia=self.estrategia.nome,
            )
        )
        resultado.decisao_de_risco = decisao
        resultado.etapas.append(Etapa(5, "Risk Manager", decisao.allowed, decisao.reason))
        return resultado

    # ------------------------------------------------------------------
    def _rodar_estrategia(self, vista, symbol: str) -> Optional[Signal]:
        try:
            contexto = de_vista(vista, symbol, papel_setup="setup", papel_tendencia="trend")
        except ValueError:
            return None
        return self.estrategia.avaliar(contexto)

    def _pendentes(self, resultado: ResultadoFinal, ate: int) -> ResultadoFinal:
        """Marca as etapas seguintes como nao executadas."""
        for i, nome in enumerate(self.ETAPAS[ate:], start=ate + 1):
            resultado.etapas.append(Etapa(i, nome, False, "nao executada", executada=False))
        return resultado
