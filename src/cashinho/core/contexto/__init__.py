"""Market Context: o ambiente de mercado, independente de estrategia.

    from cashinho.core.contexto import MotorDeContexto, fonte_yahoo

    contexto = MotorDeContexto(fonte_yahoo()).montar()
    print(contexto.market_regime, contexto.data_quality.nivel)

O contexto descreve o ambiente - Ibovespa, dolar, juros, petroleo, minerio e
indices internacionais - e diz **o quanto disso ele realmente sabe**. Ele nao
gera operacao: entra como fator adicional em um sinal que ja existe (ver
``aplicar_contexto``).
"""

from .correlacao import (
    LIMIAR_RELEVANTE,
    MIN_AMOSTRA,
    correlacao_entre,
    correlacoes_relevantes,
    pearson,
    retornos_alinhados,
)
from .fator import (
    LIMITE_DE_AJUSTE,
    EstrategiaComContexto,
    aplicar_contexto,
    fator_de_contexto,
)
from .fontes import (
    FonteBCB,
    FonteComposta,
    FonteDeContexto,
    FonteProvider,
    fonte_demo,
    fonte_yahoo,
)
from .instrumentos import (
    CATALOGO,
    DOLAR,
    IBOVESPA,
    JUROS_CDI,
    MINERIO,
    NASDAQ,
    PETROLEO,
    SP500,
    Instrumento,
    Papel,
    instrumento,
    sem_fonte_confiavel,
)
from .medidas import (
    classificar_volatilidade,
    variacao_do_dia,
    volatilidade_historica,
    volatilidade_por_candle,
)
from .modelos import (
    Correlacao,
    DirecaoDeMercado,
    EstadoDaLeitura,
    Leitura,
    MarketContext,
    NivelDeQualidade,
    NivelDeVolatilidade,
    QualidadeDeDados,
    RegimeDeMercado,
)
from .motor import ConfigContexto, MotorDeContexto
from .regime import classificar_regime
from .view import linha_do_instrumento, pagina, secao_contexto, secao_correlacoes

__all__ = [
    "MarketContext", "MotorDeContexto", "ConfigContexto",
    "Leitura", "Correlacao", "QualidadeDeDados",
    "RegimeDeMercado", "DirecaoDeMercado", "NivelDeVolatilidade",
    "NivelDeQualidade", "EstadoDaLeitura",
    "FonteDeContexto", "FonteProvider", "FonteBCB", "FonteComposta",
    "fonte_yahoo", "fonte_demo",
    "Instrumento", "Papel", "instrumento", "sem_fonte_confiavel", "CATALOGO",
    "IBOVESPA", "DOLAR", "JUROS_CDI", "PETROLEO", "MINERIO", "SP500", "NASDAQ",
    "aplicar_contexto", "fator_de_contexto", "EstrategiaComContexto",
    "LIMITE_DE_AJUSTE",
    "classificar_regime", "classificar_volatilidade", "variacao_do_dia",
    "volatilidade_por_candle", "volatilidade_historica",
    "pearson", "correlacao_entre", "correlacoes_relevantes", "retornos_alinhados",
    "MIN_AMOSTRA", "LIMIAR_RELEVANTE",
    "secao_contexto", "secao_correlacoes", "linha_do_instrumento", "pagina",
]
