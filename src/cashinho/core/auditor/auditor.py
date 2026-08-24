"""O Contrarian Auditor.

Ele nao ajuda a encontrar operacoes - ele tenta derrubar as que ja foram
encontradas. Roda as onze frentes de invalidacao, desconta do score o que
achou e devolve um veredito.

A regra que da sentido ao modulo: **uma rejeicao critica impede a aprovacao**,
por mais alto que esteja o score. Nao ha media, nao ha compensacao, nao ha
"mas o resto esta bom".
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from ..cache import CacheLimitado
from ...models import BRT
from ..oportunidade.estados import EstadoOportunidade
from ..oportunidade.modelos import Opportunity
from ..structure import EstruturaConfig, analisar_estrutura
from .checagens import CHECAGENS, ConfigAuditor, ContextoAuditoria
from .modelos import AuditResult, Checagem, Severidade


class ContrarianAuditor:
    """Advogado do diabo do sistema."""

    def __init__(
        self,
        config: Optional[ConfigAuditor] = None,
        checagens: Sequence = CHECAGENS,
        score_minimo_pos_auditoria: float = 55.0,
        estrutura: Optional[EstruturaConfig] = None,
    ):
        self.config = config or ConfigAuditor()
        self.checagens = tuple(checagens)
        self.score_minimo = score_minimo_pos_auditoria
        self.cfg_estrutura = estrutura or EstruturaConfig()
        self._cache_estrutura = CacheLimitado(teto=256)

    # ------------------------------------------------------------------
    def auditar(
        self,
        op: Opportunity,
        vista=None,
        agora: Optional[datetime] = None,
        janela: int = 400,
    ) -> AuditResult:
        """Tenta invalidar a oportunidade e devolve o veredito.

        ``vista`` e' opcional: sem ela, as checagens que dependem de dados de
        mercado saem como nao verificadas - e nao viram fator favoravel.
        """
        agora = agora or op.timestamp
        ctx = self._contexto(op, vista, agora, janela)
        checagens = tuple(c(ctx) for c in self.checagens)
        return self._veredito(op, checagens)

    # ------------------------------------------------------------------
    def _contexto(self, op: Opportunity, vista, agora: datetime, janela: int) -> ContextoAuditoria:
        ctx = ContextoAuditoria(op=op, agora=agora, cfg=self.config)
        if vista is None or not op.timeframe_setup or op.timeframe_setup == "-":
            return ctx
        try:
            serie_setup = vista.fechados(op.timeframe_setup, limite=janela)
            serie_trigger = vista.fechados(op.timeframe_trigger, limite=janela)
        except Exception:  # a vista pode nao ter aquele timeframe
            return ctx
        if len(serie_setup) < 5:
            return ctx
        ctx.serie_setup = serie_setup
        ctx.serie_trigger = serie_trigger
        ctx.estrutura = self._estrutura(serie_setup)
        return ctx

    def _estrutura(self, serie):
        chave = (serie.symbol, serie.timeframe, serie.last.ts, len(serie))
        return self._cache_estrutura.obter(
            chave, lambda: analisar_estrutura(serie, self.cfg_estrutura))

    # ------------------------------------------------------------------
    def _veredito(self, op: Opportunity, checagens: tuple[Checagem, ...]) -> AuditResult:
        criticos = [c for c in checagens if c.critica]
        alertas = [c for c in checagens if c.alerta]
        favoraveis = [c for c in checagens if c.passou and c.verificada]

        ajuste = round(sum(c.ajuste for c in checagens if not c.passou), 2)
        score_final = max(0.0, min(100.0, op.score + ajuste))

        aprovado = True
        motivo = ""
        if op.estado is not EstadoOportunidade.APROVADO:
            aprovado = False
            motivo = (
                f"a oportunidade chegou ao auditor como {op.estado.value} - "
                "o auditor nao aprova o que o engine nao aprovou"
            )
        elif criticos:
            aprovado = False
            motivo = (
                f"{len(criticos)} rejeicao(oes) critica(s): "
                + "; ".join(c.titulo for c in criticos)
            )
        elif score_final < self.score_minimo:
            aprovado = False
            motivo = (
                f"score caiu de {op.score:.0f} para {score_final:.0f} com os descontos, "
                f"abaixo do minimo de {self.score_minimo:.0f}"
            )
        else:
            motivo = (
                f"tentei invalidar em {len(checagens)} frentes; "
                f"{len(favoraveis)} nao encontraram problema"
                + (f" e {len(alertas)} viraram alerta" if alertas else "")
            )

        razoes = [c.detalhe for c in criticos]
        razoes += [c.detalhe for c in alertas]
        if not razoes:
            razoes = [c.detalhe for c in favoraveis[:3]]

        return AuditResult(
            approved=aprovado,
            warnings=tuple(f"{c.titulo}: {c.detalhe}" for c in alertas),
            critical_rejections=tuple(f"{c.titulo}: {c.detalhe}" for c in criticos),
            score_adjustment=ajuste,
            reasons=tuple(razoes),
            checagens=checagens,
            score_original=op.score,
            score_final=round(score_final, 1),
            motivo=motivo,
        )
