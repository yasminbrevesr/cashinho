"""Adaptador: o Opportunity Engine como uma Strategy.

Assim a oportunidade pontuada entra na tela Analise, no Risk Manager, no
backtest e na comparacao de timeframes sem que nenhuma dessas pecas conheca
este modulo.
"""

from __future__ import annotations

from typing import Optional

from ..strategy.base import Strategy, registrar
from ..strategy.context import StrategyContext
from ..strategy.models import Action, Factor, Signal
from .engine import OpportunityEngine
from .estados import EstadoOportunidade
from .modelos import Opportunity

AVISO = (
    "score com pesos ajustaveis e regras simples - sem otimizacao nem backtest "
    "validado; nao e' uma estrategia final nem recomendacao"
)


class EstrategiaOportunidade(Strategy):
    """Emite BUY/SELL apenas quando a oportunidade sai como SETUP APROVADO."""

    nome = "oportunidade-score"
    descricao = "confluencia multi-timeframe pontuada em onze componentes"
    timeframe_preferido = "5m"
    experimental = True
    aviso = AVISO

    def __init__(self, engine: Optional[OpportunityEngine] = None):
        self.engine = engine or OpportunityEngine()

    def avaliar(self, contexto: StrategyContext) -> Signal:
        vista = contexto.extras.get("vista")
        if vista is None:
            return self.sinal_vazio(
                contexto,
                "esta estrategia precisa da vista multi-timeframe no contexto "
                "(use cashinho.core.strategy.de_vista)",
            )

        op = self.engine.avaliar(vista, contexto.symbol)
        action = {
            EstadoOportunidade.APROVADO: Action.BUY,  # ajustado pela direcao abaixo
            EstadoOportunidade.AGUARDANDO_GATILHO: Action.WAIT,
            EstadoOportunidade.REJEITADO: Action.WAIT,
            EstadoOportunidade.NAO_OPERAR: Action.NONE,
            EstadoOportunidade.EXPIRADO: Action.NONE,
        }[op.estado]
        if op.estado.acionavel and op.direction is not None:
            action = Action.BUY if op.direction.value == "COMPRA" else Action.SELL

        razoes = op.reasons if op.reasons else (op.motivo_do_estado,)
        return Signal(
            symbol=op.symbol,
            timestamp=op.timestamp,
            timeframe=op.timeframe_setup,
            action=action,
            setup=f"{op.estado.value}: {op.setup}",
            confidence=round(op.score / 100.0, 3),
            reasons=razoes if action.acionavel else razoes[:4],
            invalidation=op.invalidation,
            strategy=self.nome,
            vies=op.direction,
            factors=_fatores(op),
            niveis=(
                {"entrada_referencia": op.entry, "stop_referencia": op.stop,
                 "alvo_referencia": op.target}
                if op.entry else {}
            ),
            experimental=True,
            aviso=AVISO,
            extras={
                "oportunidade": op,
                "multitimeframe": op.leitura,
                "avaliacoes": (),
            },
        )


def _fatores(op: Opportunity) -> tuple[Factor, ...]:
    """Cada componente do score vira um fator da tela."""
    if op.score_detalhado is None:
        return ()
    return tuple(
        Factor(
            nome=c.nome,
            favoravel=(True if c.nota >= 60 else (False if c.nota < 40 else None)),
            detalhe=f"{c.nota:.0f}/100 - {c.leitura}",
            peso=c.peso,
            obrigatorio=c.chave in ("gatilho", "risco_retorno", "suporte_resistencia"),
        )
        for c in op.score_detalhado.por_contribuicao()
    )


registrar(EstrategiaOportunidade.nome, EstrategiaOportunidade)
