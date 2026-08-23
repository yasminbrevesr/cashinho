"""A trava de saude na porta da corretora.

Quando o Market Data cai ou fica velho, o painel nao se limita a ficar
vermelho: ``BrokerComSaude`` **recusa ordem de abertura**. Mostrar OFFLINE
numa tela e deixar a ordem passar seria decorar o problema.

Como no ``BrokerComRisco``, ordem que **reduz** posicao passa sempre. Uma
trava que impede de sair de uma posicao aberta e' pior que trava nenhuma - e
com o feed caido, sair e' justamente o que mais se quer poder fazer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..broker.base import Broker
from ..broker.modelos import Balance, Operacao, Order, OrderStatus, Position
from .monitor import MonitorDeSaude


class OperacaoBloqueadaPorSaudeError(RuntimeError):
    """Ordem barrada porque o sistema nao esta em condicao de operar."""


class BrokerComSaude(Broker):
    """Corretora com o painel de saude na porta."""

    def __init__(self, broker: Broker, monitor: MonitorDeSaude,
                 levantar: bool = False):
        self.broker = broker
        self.monitor = monitor
        self.levantar = levantar
        self.bloqueadas: list[Order] = []

    @property
    def nome(self) -> str:  # type: ignore[override]
        return f"{self.broker.nome}+saude"

    @property
    def simulado(self) -> bool:  # type: ignore[override]
        return self.broker.simulado

    # ------------------------------------------------------------------
    def place_order(self, order: Order) -> Order:
        if self._reduz_posicao(order):
            return self.broker.place_order(order)

        saude = self.monitor.verificar()
        if saude.bloqueia_novas_operacoes:
            return self._recusar(order, saude.bloqueios[0])
        return self.broker.place_order(order)

    def _recusar(self, order: Order, motivo: str) -> Order:
        order.status = OrderStatus.REJEITADA
        order.motivo = f"operacao nova bloqueada - {motivo}"
        self.bloqueadas.append(order)
        if self.levantar:
            raise OperacaoBloqueadaPorSaudeError(order.motivo)
        return order

    def _reduz_posicao(self, order: Order) -> bool:
        if order.tipo.fecha_posicao:
            return True
        posicoes = {p.symbol.upper(): p for p in self.broker.get_positions()}
        p = posicoes.get(order.symbol.upper())
        if p is None:
            return False
        return (p.quantidade > 0 and not order.compra) or (p.quantidade < 0 and order.compra)

    # -- o resto passa direto -------------------------------------------
    def cancel_order(self, order_id: str) -> Order:
        return self.broker.cancel_order(order_id)

    def get_orders(self, symbol: Optional[str] = None, abertas: bool = False) -> list[Order]:
        return self.broker.get_orders(symbol, abertas)

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        return self.broker.get_positions(symbol)

    def get_balance(self) -> Balance:
        return self.broker.get_balance()

    def get_trades(self) -> list[Operacao]:
        return self.broker.get_trades()

    def cancel_all(self, symbol: Optional[str] = None) -> list[Order]:
        return self.broker.cancel_all(symbol)
