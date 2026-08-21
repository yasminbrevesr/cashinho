"""Backtest Engine do Cashinho.

    from cashinho.core.backtest import BacktestConfig, BacktestEngine
    from cashinho.core.strategy import BaselineTendenciaVolumeATR

    config = BacktestConfig(symbol="PETR4", capital_inicial=100_000)
    resultado = BacktestEngine(BaselineTendenciaVolumeATR(), config).rodar(serie_1m)

    print(resultado.metricas.retorno_total_pct, resultado.metricas.max_drawdown_pct)

O engine nao depende de interface: recebe serie e estrategia, devolve
:class:`BacktestResult`. Quem desenha e' o modulo ``view``.
"""

from .config import BacktestConfig
from .costs import SEM_CUSTOS, ModeloCustos
from .engine import BacktestEngine
from .metrics import calcular, max_drawdown, retornos_diarios, sharpe, sortino
from .models import BacktestResult, BacktestTrade, Metricas, MotivoSaida, PontoEquity
from .view import curva_de_capital, lista_de_trades, pagina, painel_metricas

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "ModeloCustos",
    "SEM_CUSTOS",
    "BacktestResult",
    "BacktestTrade",
    "PontoEquity",
    "Metricas",
    "MotivoSaida",
    "calcular",
    "sharpe",
    "sortino",
    "max_drawdown",
    "retornos_diarios",
    "pagina",
    "curva_de_capital",
    "lista_de_trades",
    "painel_metricas",
]
