"""Timeframe Advisor: em qual granularidade operar este ativo agora.

    from cashinho.core.advisor import TimeframeAdvisor

    rec = TimeframeAdvisor().avaliar(serie_de_1m)
    rec.setup_timeframe        # "5m"
    rec.market_fit_score       # 86.0
    rec.statistical_evidence_score   # None quando nao ha historico

A pergunta nao e' "qual timeframe ganhou mais hoje" - e' qual granularidade o
comportamento atual favorece, e se ha evidencia para afirmar isso. Os dois
numeros ficam separados de proposito.
"""

from .advisor import (
    CONTEXTO_CANDIDATOS,
    GATILHO_CANDIDATOS,
    SETUP_CANDIDATOS,
    ConfigAdvisor,
    TimeframeAdvisor,
)
from .amostra import (
    AMOSTRA_PLENA,
    Confianca,
    Estatistica,
    NivelDeConfianca,
    calcular_confianca,
)
from .estabilidade import (
    ConfigEstabilidade,
    Decisao,
    RecomendacaoAtual,
    decidir,
)
from .medidas import Medida, MedidasDoTimeframe, medir
from .modelos import ItemDoRanking, StatusAdvisor, TimeframeRecommendation
from .periodos import PeriodoDoPregao, periodo_de
from .score import (
    PESOS_PADRAO,
    Componente,
    PesosAdvisor,
    PesosInvalidosError,
    ScoreDoTimeframe,
    calcular,
)
from .view import card, linha_detalhada, pagina

__all__ = [
    "TimeframeAdvisor", "ConfigAdvisor", "TimeframeRecommendation",
    "ItemDoRanking", "StatusAdvisor",
    "SETUP_CANDIDATOS", "CONTEXTO_CANDIDATOS", "GATILHO_CANDIDATOS",
    "PesosAdvisor", "PESOS_PADRAO", "PesosInvalidosError", "ScoreDoTimeframe",
    "Componente", "calcular",
    "Estatistica", "Confianca", "NivelDeConfianca", "calcular_confianca",
    "AMOSTRA_PLENA",
    "ConfigEstabilidade", "RecomendacaoAtual", "Decisao", "decidir",
    "Medida", "MedidasDoTimeframe", "medir",
    "PeriodoDoPregao", "periodo_de",
    "card", "pagina", "linha_detalhada",
]
