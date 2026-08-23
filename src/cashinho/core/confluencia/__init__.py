"""Multi-Timeframe Engine: contexto, tendencia, setup e gatilho.

Duas metades, separadas de proposito:

- **alinhamento** - ``cashinho.core.mtf`` diz quais candles ja fecharam em
  cada timeframe naquele instante (e levanta ``LookaheadError`` se alguem
  tentar ler um que nao fechou);
- **leitura e regras** - este modulo diz o que cada camada significa e quando
  a combinacao autoriza uma :class:`Opportunity`.

    from cashinho.core.confluencia import MultiTimeframeEngine

    engine = MultiTimeframeEngine()               # 60m/15m/5m/1m
    resultado = engine.avaliar(vista, "PETR4")

    resultado.leitura.context.estado              # ContextState.BULLISH
    resultado.oportunidade                        # None ate uma regra fechar
"""

from .engine import (
    CAMADAS_CONFLUENCIA,
    MultiTimeframeEngine,
    ResultadoConfluencia,
    config_padrao,
)
from .estados import (
    ESTADOS_POR_PAPEL,
    PAPEIS_PADRAO,
    ContextState,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
)
from .estrategia import EstrategiaConfluencia
from .leitura import ConfigLeitura, ler_context, ler_setup, ler_trend, ler_trigger
from .modelos import (
    Camada,
    Context,
    LeituraMultiTimeframe,
    Opportunity,
    Setup,
    Trend,
    Trigger,
)
from .regras import (
    PULLBACK_A_FAVOR,
    REGRAS_PADRAO,
    REVERSAO_DE_FALSO_ROMPIMENTO,
    ROMPIMENTO_COM_CONTEXTO,
    AvaliacaoRegra,
    Checagem,
    RegraOportunidade,
)
from .view import linha_resumo, secao_multitimeframe

__all__ = [
    "MultiTimeframeEngine",
    "ResultadoConfluencia",
    "config_padrao",
    "CAMADAS_CONFLUENCIA",
    "Context",
    "Trend",
    "Setup",
    "Trigger",
    "Camada",
    "LeituraMultiTimeframe",
    "Opportunity",
    "ContextState",
    "TrendState",
    "SetupState",
    "TriggerState",
    "Vies",
    "PAPEIS_PADRAO",
    "ESTADOS_POR_PAPEL",
    "RegraOportunidade",
    "AvaliacaoRegra",
    "Checagem",
    "REGRAS_PADRAO",
    "PULLBACK_A_FAVOR",
    "ROMPIMENTO_COM_CONTEXTO",
    "REVERSAO_DE_FALSO_ROMPIMENTO",
    "ConfigLeitura",
    "ler_context",
    "ler_trend",
    "ler_setup",
    "ler_trigger",
    "EstrategiaConfluencia",
    "secao_multitimeframe",
    "linha_resumo",
]
