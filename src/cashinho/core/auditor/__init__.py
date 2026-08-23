"""Contrarian Auditor: a peca que tenta derrubar a oportunidade.

    from cashinho.core.auditor import ContrarianAuditor, Pipeline

    auditoria = ContrarianAuditor().auditar(oportunidade, vista)
    auditoria.approved              # False se houver rejeicao critica
    auditoria.critical_rejections   # o que barrou
    auditoria.score_adjustment      # quanto foi descontado do score

O fluxo obrigatorio esta em :class:`Pipeline`::

    Strategy -> Opportunity -> Score -> Auditor -> Risk Manager -> Resultado
"""

from .auditor import ContrarianAuditor
from .checagens import CHECAGENS, ConfigAuditor, ContextoAuditoria
from .modelos import AuditResult, Checagem, Severidade
from .pipeline import Etapa, Pipeline, ResultadoFinal
from .view import pagina_resultado, resumo_auditoria, secao_auditor, trilha_do_fluxo

__all__ = [
    "ContrarianAuditor",
    "AuditResult",
    "Checagem",
    "Severidade",
    "ConfigAuditor",
    "ContextoAuditoria",
    "CHECAGENS",
    "Pipeline",
    "ResultadoFinal",
    "Etapa",
    "secao_auditor",
    "resumo_auditoria",
    "trilha_do_fluxo",
    "pagina_resultado",
]
