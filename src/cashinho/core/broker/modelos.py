"""Modelos de ordem, posicao, saldo e operacao.

Vocabulario comum a qualquer corretora - o PaperBroker e uma futura ligacao
com a corretora de verdade falam a mesma lingua.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class OrderType(str, Enum):
    """Os tipos simulados."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"  # stop de entrada (vira mercado ao disparar)
    STOP_LOSS = "stop_loss"  # protecao de posicao aberta
    TAKE_PROFIT = "take_profit"  # realizacao de posicao aberta
    OCO = "oco"  # par ligado: um executa, o outro cancela

    @property
    def precisa_limite(self) -> bool:
        return self in (OrderType.LIMIT, OrderType.TAKE_PROFIT)

    @property
    def precisa_disparo(self) -> bool:
        return self in (OrderType.STOP, OrderType.STOP_LOSS)

    @property
    def fecha_posicao(self) -> bool:
        """Ordem de protecao: so faz sentido com posicao aberta."""
        return self in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT)


class OrderStatus(str, Enum):
    PENDENTE = "pendente"
    EXECUTADA = "executada"
    CANCELADA = "cancelada"
    REJEITADA = "rejeitada"

    @property
    def viva(self) -> bool:
        return self is OrderStatus.PENDENTE

    @property
    def encerrada(self) -> bool:
        return not self.viva


def novo_id(prefixo: str = "ord") -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:10]}"


@dataclass
class Order:
    """Uma ordem, do envio ao desfecho."""

    symbol: str
    side: Direction  # COMPRA ou VENDA (lado da ordem, nao da posicao)
    tipo: OrderType
    quantidade: int
    preco_limite: Optional[float] = None
    preco_disparo: Optional[float] = None
    id: str = field(default_factory=novo_id)
    status: OrderStatus = OrderStatus.PENDENTE
    criada_em: Optional[datetime] = None
    atualizada_em: Optional[datetime] = None
    preco_executado: Optional[float] = None
    executada_em: Optional[datetime] = None
    custos: float = 0.0
    oco_id: Optional[str] = None
    referencia: str = ""
    motivo: str = ""
    # onde a ideia morre - e' o que o Risk Manager usa para dimensionar.
    # Ordem de entrada sem stop nao passa pelo risco.
    stop_referencia: Optional[float] = None

    @property
    def compra(self) -> bool:
        return self.side is Direction.LONG

    @property
    def viva(self) -> bool:
        return self.status.viva

    @property
    def financeiro(self) -> float:
        preco = self.preco_executado or self.preco_limite or self.preco_disparo or 0.0
        return self.quantidade * preco

    @property
    def descricao(self) -> str:
        partes = [self.tipo.value, self.side.value.lower(), f"{self.quantidade}"]
        if self.preco_disparo is not None:
            partes.append(f"disparo {self.preco_disparo:.2f}")
        if self.preco_limite is not None:
            partes.append(f"limite {self.preco_limite:.2f}")
        return " ".join(partes)

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "tipo": self.tipo.value,
            "quantidade": self.quantidade,
            "preco_limite": self.preco_limite,
            "preco_disparo": self.preco_disparo,
            "status": self.status.value,
            "preco_executado": round(self.preco_executado, 4) if self.preco_executado else None,
            "executada_em": self.executada_em.isoformat() if self.executada_em else None,
            "custos": round(self.custos, 2),
            "oco_id": self.oco_id,
            "motivo": self.motivo,
            "stop_referencia": self.stop_referencia,
        }


@dataclass
class Position:
    """Posicao aberta. Quantidade negativa significa vendido."""

    symbol: str
    quantidade: int
    preco_medio: float
    aberta_em: datetime
    stop: Optional[float] = None
    alvo: Optional[float] = None

    @property
    def direcao(self) -> Direction:
        return Direction.LONG if self.quantidade > 0 else Direction.SHORT

    @property
    def comprada(self) -> bool:
        return self.quantidade > 0

    @property
    def exposicao(self) -> float:
        return abs(self.quantidade) * self.preco_medio

    def valor(self, preco: float) -> float:
        return self.quantidade * preco

    def pnl_aberto(self, preco: float) -> float:
        return (preco - self.preco_medio) * self.quantidade

    def para_dict(self, preco: Optional[float] = None) -> dict:
        dados = {
            "symbol": self.symbol,
            "quantidade": self.quantidade,
            "direcao": self.direcao.value,
            "preco_medio": round(self.preco_medio, 4),
            "exposicao": round(self.exposicao, 2),
            "aberta_em": self.aberta_em.isoformat(),
        }
        if preco is not None:
            dados["preco_atual"] = round(preco, 4)
            dados["pnl_aberto"] = round(self.pnl_aberto(preco), 2)
        return dados


@dataclass(frozen=True)
class Operacao:
    """Uma operacao encerrada - o registro que vira historico."""

    symbol: str
    direcao: Direction
    quantidade: int
    preco_entrada: float
    preco_saida: float
    aberta_em: datetime
    fechada_em: datetime
    custos: float
    motivo: str = ""

    @property
    def resultado_bruto(self) -> float:
        sinal = 1 if self.direcao is Direction.LONG else -1
        return (self.preco_saida - self.preco_entrada) * self.quantidade * sinal

    @property
    def resultado(self) -> float:
        return self.resultado_bruto - self.custos

    @property
    def venceu(self) -> bool:
        return self.resultado > 0

    @property
    def dia(self) -> date:
        return self.fechada_em.date()

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direcao": self.direcao.value,
            "quantidade": self.quantidade,
            "preco_entrada": round(self.preco_entrada, 4),
            "preco_saida": round(self.preco_saida, 4),
            "aberta_em": self.aberta_em.isoformat(),
            "fechada_em": self.fechada_em.isoformat(),
            "custos": round(self.custos, 2),
            "resultado": round(self.resultado, 2),
            "motivo": self.motivo,
        }


@dataclass
class Balance:
    """Saldo, patrimonio e resultado."""

    saldo: float  # caixa livre
    patrimonio: float  # caixa + posicoes a mercado
    exposicao: float
    pnl_dia: float
    pnl_acumulado: float
    capital_inicial: float
    posicoes_abertas: int = 0
    ordens_abertas: int = 0
    custos_totais: float = 0.0

    @property
    def retorno_pct(self) -> float:
        if not self.capital_inicial:
            return 0.0
        return (self.patrimonio - self.capital_inicial) / self.capital_inicial * 100.0

    def para_dict(self) -> dict:
        return {
            "saldo": round(self.saldo, 2),
            "patrimonio": round(self.patrimonio, 2),
            "exposicao": round(self.exposicao, 2),
            "pnl_dia": round(self.pnl_dia, 2),
            "pnl_acumulado": round(self.pnl_acumulado, 2),
            "retorno_pct": round(self.retorno_pct, 3),
            "capital_inicial": round(self.capital_inicial, 2),
            "posicoes_abertas": self.posicoes_abertas,
            "ordens_abertas": self.ordens_abertas,
            "custos_totais": round(self.custos_totais, 2),
        }
