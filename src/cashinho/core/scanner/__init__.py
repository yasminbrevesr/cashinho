"""Scanner B3: varre uma watchlist com o pipeline completo e ranqueia.

    from cashinho.core.scanner import ScannerB3, ScannerConfig
    from cashinho.data.synthetic import SyntheticProvider

    scanner = ScannerB3(SyntheticProvider(), ScannerConfig(watchlist=("PETR4", "VALE3")))
    resultado = scanner.varrer()

    resultado.tem_oportunidades      # False e' um resultado valido
    resultado.ranking("score")       # a watchlist ordenada

Por ativo: Market Data -> Context -> Multi-Timeframe -> Strategy ->
Opportunity -> Score -> Auditor -> Risk Manager.
"""

from .config import (
    ORDENACOES,
    WATCHLIST_PADRAO,
    ConfiguracaoInvalidaError,
    ScannerConfig,
)
from .filtros import FILTROS, Filtro, aplicar
from .scanner import LinhaScanner, ResultadoScanner, ScannerB3, StatusAtivo
from .view import detalhe, faixa_sem_oportunidade, linha_da_tabela, pagina, tabela

__all__ = [
    "ScannerB3",
    "ScannerConfig",
    "ResultadoScanner",
    "LinhaScanner",
    "StatusAtivo",
    "Filtro",
    "FILTROS",
    "aplicar",
    "WATCHLIST_PADRAO",
    "ORDENACOES",
    "ConfiguracaoInvalidaError",
    "pagina",
    "tabela",
    "linha_da_tabela",
    "detalhe",
    "faixa_sem_oportunidade",
]
