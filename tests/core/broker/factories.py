"""Brokers e ordens para os testes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from cashinho.core.backtest.costs import SEM_CUSTOS, ModeloCustos
from cashinho.core.broker import BrokerComRisco, ConfigPaper, Order, OrderType, PaperBroker
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.models import BRT, Candle, Direction

AGORA = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)


def relogio(momento: datetime = AGORA):
    return lambda: momento


def paper(capital: float = 100_000.0, custos: Optional[ModeloCustos] = None,
          preco: Optional[float] = 31.00, symbol: str = "PETR4", **campos) -> PaperBroker:
    b = PaperBroker(
        ConfigPaper(capital_inicial=capital, custos=custos or SEM_CUSTOS, **campos),
        relogio(),
    )
    if preco is not None:
        b.atualizar_preco(symbol, preco)
    return b


def risco_folgado(capital: float = 100_000.0, **campos) -> RiskManager:
    base = dict(capital=capital, risco_por_trade_pct=1.0, max_trades_dia=200,
                perda_max_diaria_pct=100.0, max_perdas_consecutivas=200,
                exposicao_max_por_ativo_pct=100.0, exposicao_max_total_pct=100.0)
    base.update(campos)
    return RiskManager(RiskConfig(**base), RiskState(capital_inicial=capital))


def com_risco(broker: Optional[PaperBroker] = None,
              risco: Optional[RiskManager] = None) -> BrokerComRisco:
    return BrokerComRisco(broker or paper(), risco or risco_folgado())


def ordem(tipo: OrderType = OrderType.MARKET, side: Direction = Direction.LONG,
          quantidade: int = 100, symbol: str = "PETR4", **campos) -> Order:
    return Order(symbol=symbol, side=side, tipo=tipo, quantidade=quantidade, **campos)


def candle(abertura: float, maxima: float, minima: float, fechamento: float,
           minuto: int = 5, volume: float = 100_000.0) -> Candle:
    return Candle(AGORA + timedelta(minutes=minuto), abertura, maxima, minima,
                  fechamento, volume)
