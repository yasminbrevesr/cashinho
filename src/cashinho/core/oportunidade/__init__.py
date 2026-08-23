"""Opportunity Engine e sistema de score.

    from cashinho.core.oportunidade import OpportunityEngine, pagina_oportunidade

    engine = OpportunityEngine()
    mtf = engine.alimentar(serie_1m)
    op = engine.avaliar(mtf.agora(), "PETR4")

    op.estado          # SETUP APROVADO / AGUARDANDO GATILHO / ...
    op.score           # 0 a 100
    op.score_detalhado # as onze notas, com peso, contribuicao e leitura

O score nunca e' caixa-preta: cada componente carrega a frase que justifica a
propria nota, e a tela mostra todos - inclusive os que puxaram para baixo.
"""

from .engine import ConfigOportunidade, OpportunityEngine
from .estados import EstadoOportunidade
from .estrategia import EstrategiaOportunidade
from .modelos import Opportunity
from .score import (
    AVALIADORES,
    NOMES,
    PESOS_PADRAO,
    ComponenteScore,
    ConfigScore,
    ContextoScore,
    PesosInvalidosError,
    PesosScore,
    ScoreDetalhado,
    calcular,
    montar_contexto,
)
from .view import (
    barra,
    faixa_de_estado,
    linha_de_lista,
    pagina_oportunidade,
    painel_score,
    resumo_score,
)

__all__ = [
    "OpportunityEngine",
    "ConfigOportunidade",
    "Opportunity",
    "EstadoOportunidade",
    "EstrategiaOportunidade",
    "PesosScore",
    "PESOS_PADRAO",
    "PesosInvalidosError",
    "ComponenteScore",
    "ScoreDetalhado",
    "ContextoScore",
    "ConfigScore",
    "calcular",
    "montar_contexto",
    "AVALIADORES",
    "NOMES",
    "pagina_oportunidade",
    "painel_score",
    "faixa_de_estado",
    "resumo_score",
    "linha_de_lista",
    "barra",
]
