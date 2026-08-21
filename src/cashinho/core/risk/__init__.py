"""Risk Manager do Cashinho - independente de estrategia.

    from cashinho.core.risk import PedidoOperacao, RiskConfig, RiskManager
    from cashinho.models import Direction

    rm = RiskManager(RiskConfig(capital=50_000, risco_por_trade_pct=1.0))
    decisao = rm.avaliar(PedidoOperacao("PETR4", Direction.LONG, entrada=31.00, stop=30.70))

    if decisao.allowed:
        rm.abrir(decisao)          # so passa decisao aprovada, emitida por este gerente

O modulo nao conhece indicador, setup nem score: recebe ativo, direcao,
entrada e stop, aplica os limites e responde. Uma rejeicao nao pode ser
revertida por quem pediu.
"""

from .config import PADRAO, ConfiguracaoInvalidaError, RiskConfig
from .manager import RiskManager
from .models import (
    KillSwitch,
    LimiteUso,
    Limitador,
    MotivoRejeicao,
    PedidoOperacao,
    Position,
    Rejeicao,
    RiskDecision,
    RiskRejectionError,
    RiskStatus,
    TradeResult,
)
from .sizing import (
    Dimensionamento,
    ajusta_ao_lote,
    dimensionar,
    quantidade_por_financeiro,
    quantidade_por_risco,
    risco_monetario,
    risco_por_acao,
)
from .state import RiskState
from .view import decisao as ver_decisao
from .view import faixa, pagina, resumo

__all__ = [
    "RiskManager",
    "RiskConfig",
    "RiskState",
    "RiskDecision",
    "RiskStatus",
    "RiskRejectionError",
    "PedidoOperacao",
    "Position",
    "TradeResult",
    "KillSwitch",
    "Rejeicao",
    "MotivoRejeicao",
    "Limitador",
    "LimiteUso",
    "ConfiguracaoInvalidaError",
    "PADRAO",
    "Dimensionamento",
    "dimensionar",
    "risco_monetario",
    "risco_por_acao",
    "quantidade_por_risco",
    "quantidade_por_financeiro",
    "ajusta_ao_lote",
    "pagina",
    "faixa",
    "resumo",
    "ver_decisao",
]
