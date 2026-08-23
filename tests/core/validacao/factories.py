"""Series e configuracoes para os testes de validacao."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from cashinho.core.backtest.config import BacktestConfig
from cashinho.core.backtest.costs import SEM_CUSTOS
from cashinho.core.risk import RiskConfig
from cashinho.core.validacao import ConfigValidacao
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 3, 10, 0, tzinfo=BRT)  # segunda


def serie_de_dias(dias: int = 10, candles_por_dia: int = 60, symbol: str = "PETR4",
                  passo: float = 0.0004) -> Series:
    """Serie com N pregoes, um candle por minuto."""
    candles = []
    preco = 30.0
    dia = ABERTURA
    adicionados = 0
    while adicionados < dias:
        if dia.weekday() < 5:
            for i in range(candles_por_dia):
                abertura = preco
                preco = preco * (1 + passo)
                candles.append(Candle(
                    dia + timedelta(minutes=i), abertura,
                    max(abertura, preco) * 1.0015, min(abertura, preco) * 0.9985,
                    preco, 20_000.0,
                ))
            adicionados += 1
        dia += timedelta(days=1)
        dia = dia.replace(hour=10, minute=0)
    return Series(symbol, "1m", candles)


def config_validacao(**campos) -> ConfigValidacao:
    base = dict(backtest=BacktestConfig(
        symbol="PETR4", capital_inicial=100_000.0, custos=SEM_CUSTOS,
        risco=RiskConfig(capital=100_000.0, risco_por_trade_pct=0.5, max_trades_dia=20,
                         max_perdas_consecutivas=20, perda_max_diaria_pct=100.0),
    ), dias_de_aquecimento=0)
    base.update(campos)
    return ConfigValidacao(**base)


def medidas(particao, retorno=5.0, drawdown=2.0, pf=1.8, sharpe=1.2,
            expectancy=50.0, trades=40, dias=10):
    from cashinho.core.validacao import Medidas

    return Medidas(particao=particao, retorno_pct=retorno, max_drawdown_pct=drawdown,
                   profit_factor=pf, sharpe=sharpe, expectancy=expectancy,
                   n_trades=trades, dias=dias)
