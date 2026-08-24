"""A trava: nenhuma ordem chega a corretora sem passar pelo Risk Manager.

``BrokerComRisco`` implementa a mesma interface ``Broker`` e embrulha
qualquer corretora - a simulada de hoje e a de verdade de amanha. Quem chama
nao percebe a diferenca; o que muda e' que a ordem so e' repassada depois de
o risco aprovar, **e com a quantidade que o risco autorizou**.

Duas decisoes que valem explicacao:

- ordem que **reduz** posicao (stop loss, take profit, encerramento manual)
  passa direto. Uma trava que impede de sair de uma posicao aberta seria pior
  do que trava nenhuma;
- ordem de entrada **sem stop** e' rejeitada aqui mesmo: sem stop nao ha risco
  por acao, e sem risco por acao nao ha dimensionamento possivel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...models import BRT, Direction
from ..log import RegistradorNulo
from ..risk import PedidoOperacao, RiskDecision, RiskManager, RiskRejectionError
from .base import Broker
from .modelos import Balance, Operacao, Order, OrderStatus, OrderType, Position


class BrokerComRisco(Broker):
    """Corretora com o Risk Manager na porta."""

    def __init__(self, broker: Broker, risco: RiskManager, referencia: str = "",
                 log=None):
        self.broker = broker
        self.risco = risco
        self.referencia = referencia
        # sem log configurado, nada e' gravado - o comportamento nao muda
        self.log = log or RegistradorNulo()
        self._decisoes: dict[str, RiskDecision] = {}
        self._rejeitadas: dict[str, Order] = {}
        self._registradas: set[str] = set()
        self.avisos: list[str] = []

    @property
    def nome(self) -> str:  # type: ignore[override]
        return f"{self.broker.nome}+risco"

    @property
    def simulado(self) -> bool:  # type: ignore[override]
        return self.broker.simulado

    # ------------------------------------------------------------------
    def place_order(self, order: Order) -> Order:
        """Avalia no risco e so entao repassa."""
        if self._reduz_posicao(order):
            enviada = self.broker.place_order(order)
            self._sincronizar()
            return enviada

        # a trava vem antes de tudo: se o risco esta bloqueado, o motivo dele
        # e' mais importante do que qualquer pendencia da ordem
        bloqueios = self.risco.bloqueios()
        if bloqueios:
            return self._rejeitar(order, f"risco: {bloqueios[0].mensagem}")

        if order.stop_referencia is None:
            return self._rejeitar(
                order,
                "o Risk Manager nao dimensiona ordem de entrada sem stop de referencia",
            )

        entrada = order.preco_limite or order.preco_disparo or self._preco(order.symbol)
        if entrada is None:
            return self._rejeitar(order, "sem preco de referencia para avaliar o risco")

        decisao = self.risco.avaliar(
            PedidoOperacao(
                symbol=order.symbol,
                direcao=order.side,
                entrada=entrada,
                stop=order.stop_referencia,
                referencia=order.referencia or self.referencia,
            )
        )
        if not decisao.allowed:
            return self._rejeitar(order, f"risco: {decisao.reason}")

        # a quantidade quem manda e' o risco - o pedido pode ser menor, nunca maior
        if order.quantidade > decisao.position_size:
            order.quantidade = decisao.position_size
        if order.quantidade <= 0:
            return self._rejeitar(order, "risco autorizou quantidade zero")

        self._decisoes[order.id] = decisao
        enviada = self.broker.place_order(order)
        if enviada.status is OrderStatus.REJEITADA:
            self._decisoes.pop(order.id, None)
        self._sincronizar()
        return enviada

    def place_oco(self, stop_loss: Order, take_profit: Order):
        """Par OCO de protecao: passa direto, porque reduz posicao."""
        if not hasattr(self.broker, "place_oco"):
            raise NotImplementedError(f"{self.broker.nome} nao simula OCO")
        return self.broker.place_oco(stop_loss, take_profit)

    def cancel_order(self, order_id: str) -> Order:
        if order_id in self._rejeitadas:
            return self._rejeitadas[order_id]
        return self.broker.cancel_order(order_id)

    def get_orders(self, symbol: Optional[str] = None, abertas: bool = False) -> list[Order]:
        ordens = list(self.broker.get_orders(symbol, abertas))
        if not abertas:
            barradas = [
                o for o in self._rejeitadas.values()
                if not symbol or o.symbol.upper() == symbol.upper()
            ]
            ordens.extend(barradas)
        return sorted(ordens, key=lambda o: (o.criada_em or datetime.min.replace(tzinfo=BRT), o.id))

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        return self.broker.get_positions(symbol)

    def get_balance(self) -> Balance:
        return self.broker.get_balance()

    def get_trades(self) -> list[Operacao]:
        return self.broker.get_trades()

    # ------------------------------------------------------------------
    def processar(self, symbol: str, candle) -> list[Order]:
        """Avanca o mercado na corretora e reconcilia o risco com o que executou."""
        executadas = self.broker.processar(symbol, candle)
        self._sincronizar()
        return executadas

    def acionar_kill_switch(self, motivo: str = "acionado manualmente") -> list[Order]:
        """Trava dos dois lados: o risco para de aprovar e a corretora para de executar."""
        self.risco.acionar_kill_switch(motivo)
        if hasattr(self.broker, "acionar_kill_switch"):
            return self.broker.acionar_kill_switch(motivo)
        return self.cancel_all()

    def liberar_kill_switch(self) -> None:
        self.risco.liberar_kill_switch()
        if hasattr(self.broker, "liberar_kill_switch"):
            self.broker.liberar_kill_switch()

    # ------------------------------------------------------------------
    def _reduz_posicao(self, order: Order) -> bool:
        if order.tipo.fecha_posicao:
            return True
        posicoes = {p.symbol.upper(): p for p in self.broker.get_positions()}
        p = posicoes.get(order.symbol.upper())
        if p is None:
            return False
        return (p.quantidade > 0 and not order.compra) or (p.quantidade < 0 and order.compra)

    def _rejeitar(self, order: Order, motivo: str) -> Order:
        self.log.aviso("risk_manager", f"ordem barrada: {motivo}",
                       symbol=order.symbol, quantidade=order.quantidade)
        order.status = OrderStatus.REJEITADA
        order.motivo = motivo
        order.criada_em = order.criada_em or datetime.now(BRT)
        order.atualizada_em = order.criada_em
        self._rejeitadas[order.id] = order
        return order

    def _preco(self, symbol: str) -> Optional[float]:
        precos = getattr(self.broker, "_precos", {})
        return precos.get(symbol.upper())

    def _sincronizar(self) -> None:
        """Espelha no Risk Manager o que a corretora executou.

        O risco precisa saber de posicao aberta e de resultado realizado para
        que exposicao, perda diaria e numero de trades signifiquem alguma
        coisa. Divergencia entre os dois lados vira aviso, nunca excecao: a
        corretora ja executou, e travar o processo aqui nao desfaz nada.
        """
        for order in self.broker.get_orders():
            if order.status is not OrderStatus.EXECUTADA or order.id in self._registradas:
                continue
            self._registradas.add(order.id)
            decisao = self._decisoes.pop(order.id, None)
            try:
                if decisao is not None:
                    # a quantidade que vale e' a que executou, nao a autorizada
                    self.risco.abrir(decisao, preco_execucao=order.preco_executado,
                                     quantidade=order.quantidade)
                elif order.symbol.upper() in self.risco.estado.posicoes:
                    self.risco.fechar(order.symbol, order.preco_executado, custos=order.custos)
            except (RiskRejectionError, KeyError, ValueError) as e:
                aviso = f"risco fora de sincronia com a corretora em {order.symbol}: {e}"
                self.avisos.append(aviso)
                # divergencia entre o risco e o que a corretora executou e' a
                # coisa mais importante que este modulo tem a dizer: ela some
                # da memoria no fim do processo, mas nao do arquivo
                self.log.erro("risk_manager", aviso, symbol=order.symbol,
                              ordem=order.id, quantidade=order.quantidade)
