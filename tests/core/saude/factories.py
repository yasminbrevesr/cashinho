"""Telemetria, monitores e brokers para os testes de saude."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from cashinho.core.broker import PaperBroker
from cashinho.core.broker.modelos import Order, OrderType
from cashinho.core.broker.paper import ConfigPaper
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.core.saude import (
    ConfigSaude,
    LimiaresSaude,
    Modo,
    MonitorDeSaude,
    Telemetria,
)
from cashinho.models import BRT, Direction

# uma quinta-feira as 14h30, dentro do pregao
AGORA = datetime(2026, 8, 20, 14, 30, tzinfo=BRT)


def telemetria(agora: datetime = AGORA, market_data_min: Optional[float] = 1.0,
               **anotacoes) -> Telemetria:
    t = Telemetria(relogio=lambda: agora)
    if market_data_min is not None:
        t.sucesso("market_data", latencia_ms=300,
                  dado_em=agora - timedelta(minutes=market_data_min))
    for chave, minutos in anotacoes.items():
        t.sucesso(chave, dado_em=agora - timedelta(minutes=minutos))
    return t


def paper(capital: float = 100_000.0) -> PaperBroker:
    broker = PaperBroker(ConfigPaper(capital_inicial=capital))
    broker.atualizar_preco("PETR4", 30.0)
    return broker


def risco(capital: float = 100_000.0, **campos) -> RiskManager:
    base = dict(capital=capital, risco_por_trade_pct=1.0, max_trades_dia=200,
                perda_max_diaria_pct=100.0, max_perdas_consecutivas=200)
    base.update(campos)
    return RiskManager(RiskConfig(**base), RiskState(capital_inicial=capital))


def monitor(agora: datetime = AGORA, t: Optional[Telemetria] = None,
            config: Optional[ConfigSaude] = None, **campos) -> MonitorDeSaude:
    return MonitorDeSaude(t or telemetria(agora), config,
                          relogio=lambda: agora, **campos)


def ordem(compra: bool = True, tipo: OrderType = OrderType.MARKET,
          quantidade: int = 100, symbol: str = "PETR4", **campos) -> Order:
    return Order(symbol=symbol, side=Direction.LONG if compra else Direction.SHORT,
                 tipo=tipo, quantidade=quantidade, **campos)
