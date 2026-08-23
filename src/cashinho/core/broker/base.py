"""A interface Broker - independente de quem executa do outro lado.

O PaperBroker implementa isto simulando; uma ligacao com a corretora de
verdade implementaria o mesmo contrato. Quem chama (pagina, scanner, robo)
nao precisa saber qual dos dois esta ali.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence

from .modelos import Balance, Operacao, Order, Position


class BrokerError(RuntimeError):
    """Erro generico de corretora."""


class OrdemInvalidaError(BrokerError):
    """A ordem nao faz sentido (preco faltando, quantidade zero...)."""


class OrdemBloqueadaError(BrokerError):
    """A ordem foi barrada antes de chegar a corretora."""


class SaldoInsuficienteError(BrokerError):
    """Nao ha caixa para a ordem."""


class Broker(ABC):
    """Contrato minimo de uma corretora."""

    nome: str = "broker"
    simulado: bool = True

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Envia uma ordem. Devolve a ordem com id e status atualizados."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """Cancela uma ordem pendente."""

    @abstractmethod
    def get_orders(self, symbol: Optional[str] = None, abertas: bool = False) -> list[Order]:
        """Ordens conhecidas, opcionalmente filtradas."""

    @abstractmethod
    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """Posicoes abertas."""

    @abstractmethod
    def get_balance(self) -> Balance:
        """Saldo, patrimonio e resultado."""

    # -- opcionais, com padrao ------------------------------------------
    def get_trades(self) -> list[Operacao]:
        """Operacoes ja encerradas."""
        return []

    def cancel_all(self, symbol: Optional[str] = None) -> list[Order]:
        canceladas = []
        for o in self.get_orders(symbol, abertas=True):
            canceladas.append(self.cancel_order(o.id))
        return canceladas
