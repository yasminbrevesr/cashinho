"""Provedores de dados de mercado."""

from .cotacao import Cotacao, cotacao_indisponivel
from .fabrica import ProvedorDesconhecidoError, catalogo, construir, montar_servico
from .mercado import MarketDataProvider, limite_de_stale
from .qualidade import (
    ConfigQualidade,
    Gravidade,
    Problema,
    Qualidade,
    ValidadorDeQualidade,
)
from .rate_limit import Freio
from .servico import (
    Finalidade,
    Leitura,
    MarketDataService,
    TempoRealIndisponivelError,
)
from .status import Capacidades, CapacidadeAusenteError, StatusDados, exigir, pior_status
