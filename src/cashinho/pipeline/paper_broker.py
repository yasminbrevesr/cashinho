"""Motor local e persistente de ordens PAPER.

Nao importa MetaTrader5 e nao possui caminho de execucao real.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from cashinho.domain.market import Candle, Quote
from cashinho.pipeline.paper_ticket import PaperTicket


class PaperOrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PaperOrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CANCELLED = "CANCELLED"
    STOPPED = "STOPPED"
    TARGETED = "TARGETED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class PaperOrder:
    id: str
    ticket: PaperTicket
    order_type: PaperOrderType
    status: PaperOrderStatus
    created_at: datetime
    filled_at: datetime | None = None
    fill_price: Decimal | None = None
    closed_at: datetime | None = None
    close_price: Decimal | None = None
    close_reason: str | None = None
    decision_key: str | None = None


class PaperOrderObserver(Protocol):
    """Observador de auditoria; não participa das regras de execução."""

    def on_order_changed(self, order: PaperOrder) -> None: ...


class PaperOrderRepository:
    """Porta minima para armazenamento de ordens simuladas."""

    def add(self, order: PaperOrder) -> None:
        raise NotImplementedError

    def get(self, order_id: str) -> PaperOrder | None:
        raise NotImplementedError

    def list(self) -> list[PaperOrder]:
        raise NotImplementedError

    def save(self, order: PaperOrder) -> None:
        raise NotImplementedError

    def last_processed(self, key: str) -> datetime | None:
        raise NotImplementedError

    def mark_processed(self, key: str, close_time: datetime) -> None:
        raise NotImplementedError


class InMemoryPaperOrderRepository(PaperOrderRepository):
    def __init__(self) -> None:
        self._orders: dict[str, PaperOrder] = {}
        self._processed: dict[str, datetime] = {}

    def add(self, order: PaperOrder) -> None:
        self._orders[order.id] = order

    def get(self, order_id: str) -> PaperOrder | None:
        return self._orders.get(order_id)

    def list(self) -> list[PaperOrder]:
        return list(self._orders.values())

    def save(self, order: PaperOrder) -> None:
        if order.id not in self._orders:
            raise KeyError(order.id)
        self._orders[order.id] = order

    def last_processed(self, key: str) -> datetime | None:
        return self._processed.get(key)

    def mark_processed(self, key: str, close_time: datetime) -> None:
        self._processed[key] = close_time


class JsonPaperOrderRepository(InMemoryPaperOrderRepository):
    """Persistencia local atomica, independente do ciclo do Streamlit."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        if path.exists():
            for raw in json.loads(path.read_text(encoding="utf-8")):
                ticket_raw = raw.pop("ticket")
                ticket = PaperTicket(
                    **{
                        **ticket_raw,
                        **{
                            key: Decimal(ticket_raw[key])
                            for key in (
                                "entry",
                                "stop",
                                "target",
                                "risk_per_share",
                                "monetary_risk",
                                "notional",
                                "risk_reward",
                            )
                        },
                    }
                )
                order = PaperOrder(
                    id=raw["id"],
                    ticket=ticket,
                    order_type=PaperOrderType(raw["order_type"]),
                    status=PaperOrderStatus(raw["status"]),
                    created_at=datetime.fromisoformat(raw["created_at"]),
                    filled_at=datetime.fromisoformat(raw["filled_at"])
                    if raw["filled_at"]
                    else None,
                    fill_price=Decimal(raw["fill_price"]) if raw["fill_price"] else None,
                    closed_at=datetime.fromisoformat(raw["closed_at"])
                    if raw["closed_at"]
                    else None,
                    close_price=Decimal(raw["close_price"]) if raw["close_price"] else None,
                    close_reason=raw["close_reason"],
                    decision_key=raw.get("decision_key"),
                )
                self._orders[order.id] = order
        marker_path = path.with_suffix(".processed.json")
        self._marker_path = marker_path
        if marker_path.exists():
            self._processed = {
                key: datetime.fromisoformat(value)
                for key, value in json.loads(marker_path.read_text(encoding="utf-8")).items()
            }

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for order in self.list():
            row = asdict(order)
            row = json.loads(json.dumps(row, default=str))
            rows.append(row)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self._path)

    def add(self, order: PaperOrder) -> None:
        super().add(order)
        self._flush()

    def save(self, order: PaperOrder) -> None:
        super().save(order)
        self._flush()

    def mark_processed(self, key: str, close_time: datetime) -> None:
        super().mark_processed(key, close_time)
        temp = self._marker_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps({name: value.isoformat() for name, value in self._processed.items()}),
            encoding="utf-8",
        )
        temp.replace(self._marker_path)


class PaperBroker:
    def __init__(
        self,
        repository: PaperOrderRepository,
        *,
        observer: PaperOrderObserver | None = None,
    ) -> None:
        self._repository = repository
        self._observer = observer

    def register(
        self,
        ticket: PaperTicket,
        order_type: PaperOrderType,
        *,
        quote: Quote | None = None,
        now: datetime,
        decision_key: str | None = None,
    ) -> PaperOrder:
        created_at = now
        if order_type is PaperOrderType.MARKET:
            if quote is None or not quote.has_active_book:
                raise ValueError(
                    "Ordem a mercado PAPER exige bid/ask real e ativo; simulacao bloqueada."
                )
            fill = quote.ask if ticket.side == "BUY" else quote.bid
            assert fill is not None
            order = PaperOrder(
                str(uuid4()),
                ticket,
                order_type,
                PaperOrderStatus.OPEN,
                created_at,
                created_at,
                fill,
                decision_key=decision_key,
            )
        else:
            order = PaperOrder(
                str(uuid4()),
                ticket,
                order_type,
                PaperOrderStatus.PENDING,
                created_at,
                decision_key=decision_key,
            )
        self._repository.add(order)
        self._publish(order)
        return order

    def list_orders(self) -> list[PaperOrder]:
        return self._repository.list()

    def cancel_order(self, order_id: str) -> PaperOrder:
        order = self._required(order_id)
        if order.status is not PaperOrderStatus.PENDING:
            raise ValueError("Somente uma ordem PAPER PENDING pode ser cancelada.")
        cancelled = replace(order, status=PaperOrderStatus.CANCELLED)
        self._repository.save(cancelled)
        self._publish(cancelled)
        return cancelled

    def close_position(
        self,
        order_id: str,
        *,
        price: Decimal,
        closed_at: datetime,
        reason: str = "MANUAL",
    ) -> PaperOrder:
        """Encerra uma posição PAPER; não cancela sua ordem de entrada."""
        order = self._required(order_id)
        if order.status is not PaperOrderStatus.OPEN:
            raise ValueError("Somente uma posicao PAPER OPEN pode ser encerrada.")
        if price <= 0:
            raise ValueError("Preco de fechamento deve ser maior que zero.")
        if order.filled_at is not None and closed_at < order.filled_at:
            raise ValueError("Horario de fechamento nao pode preceder a abertura.")
        allowed_reasons = {
            "MANUAL",
            "RISK_EXIT",
            "THESIS_INVALIDATED",
            "OPPOSITE_SIGNAL",
            "CONTEXT_REVERSAL",
        }
        if reason not in allowed_reasons:
            raise ValueError("Motivo de fechamento PAPER inválido.")
        closed = replace(
            order,
            status=PaperOrderStatus.CLOSED,
            closed_at=closed_at,
            close_price=price,
            close_reason=reason,
        )
        self._repository.save(closed)
        self._publish(closed)
        return closed

    def process_candle(
        self, candle: Candle, *, symbol: str | None = None, timeframe: str = "UNKNOWN"
    ) -> list[PaperOrder]:
        if not candle.is_closed:
            raise ValueError("Paper Broker processa somente candles fechados.")
        key = f"{symbol or '*'}:{timeframe}"
        previous_close = self._repository.last_processed(key)
        if previous_close is not None and candle.close_time <= previous_close:
            return []
        changed: list[PaperOrder] = []
        for order in self._repository.list():
            if symbol is not None and order.ticket.symbol != symbol:
                continue
            if (
                timeframe != "UNKNOWN"
                and order.ticket.timeframe is not None
                and order.ticket.timeframe != timeframe
            ):
                continue
            if candle.close_time <= order.created_at:
                continue
            updated = self._process(order, candle)
            if updated != order:
                self._repository.save(updated)
                self._publish(updated)
                changed.append(updated)
        self._repository.mark_processed(key, candle.close_time)
        return changed

    def _process(self, order: PaperOrder, candle: Candle) -> PaperOrder:
        if order.status is PaperOrderStatus.PENDING:
            touched = candle.low <= order.ticket.entry <= candle.high
            if not touched:
                return order
            order = replace(
                order,
                status=PaperOrderStatus.OPEN,
                filled_at=candle.close_time,
                fill_price=order.ticket.entry,
            )
        if order.status is not PaperOrderStatus.OPEN:
            return order
        ticket = order.ticket
        stop_hit = candle.low <= ticket.stop if ticket.side == "BUY" else candle.high >= ticket.stop
        target_hit = (
            candle.high >= ticket.target if ticket.side == "BUY" else candle.low <= ticket.target
        )
        # Sem dados intrabar, se ambos forem tocados assume stop (cenario conservador).
        if stop_hit:
            return replace(
                order,
                status=PaperOrderStatus.STOPPED,
                closed_at=candle.close_time,
                close_price=ticket.stop,
                close_reason="STOP",
            )
        if target_hit:
            return replace(
                order,
                status=PaperOrderStatus.TARGETED,
                closed_at=candle.close_time,
                close_price=ticket.target,
                close_reason="TARGET",
            )
        return order

    def _required(self, order_id: str) -> PaperOrder:
        order = self._repository.get(order_id)
        if order is None:
            raise KeyError(order_id)
        return order

    def _publish(self, order: PaperOrder) -> None:
        if self._observer is not None:
            self._observer.on_order_changed(order)
