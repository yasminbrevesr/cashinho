"""Corretoras: a interface Broker e a implementacao simulada.

    from cashinho.core.broker import BrokerComRisco, PaperBroker
    from cashinho.core.risk import RiskManager

    broker = BrokerComRisco(PaperBroker(), RiskManager())
    broker.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 500,
                             stop_referencia=30.70))

``BrokerComRisco`` embrulha qualquer corretora e garante o que o sistema
exige: nenhuma ordem de entrada chega a corretora sem passar pelo Risk
Manager, e a quantidade e' a que o risco autorizou.
"""

from .base import (
    Broker,
    BrokerError,
    OrdemBloqueadaError,
    OrdemInvalidaError,
    SaldoInsuficienteError,
)
from .modelos import (
    Balance,
    Operacao,
    Order,
    OrderStatus,
    OrderType,
    Position,
)
from .paper import ConfigPaper, PaperBroker
from .risco import BrokerComRisco
from .view import faixa_kill_switch, pagina, painel_saldo, tabela_operacoes, tabela_ordens, tabela_posicoes

__all__ = [
    "Broker",
    "PaperBroker",
    "ConfigPaper",
    "BrokerComRisco",
    "Order",
    "OrderType",
    "OrderStatus",
    "Position",
    "Balance",
    "Operacao",
    "BrokerError",
    "OrdemInvalidaError",
    "OrdemBloqueadaError",
    "SaldoInsuficienteError",
    "pagina",
    "painel_saldo",
    "tabela_posicoes",
    "tabela_ordens",
    "tabela_operacoes",
    "faixa_kill_switch",
]
