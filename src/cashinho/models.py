"""Modelos de dados do Cashinho.

Tudo aqui e' stdlib puro: o nucleo de analise nao depende de pandas/numpy,
para que o robo rode em qualquer maquina com Python 3.9+.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Iterable, Optional, Sequence

# Fuso de Brasilia. Usamos offset fixo (-03:00) porque o Brasil nao tem
# horario de verao desde 2019 e assim evitamos depender do tzdata do sistema.
BRT = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

TICK_ACAO = 0.01  # variacao minima de precos de acoes na B3
LOTE_PADRAO = 100


class Direction(str, Enum):
    """Direcao de uma operacao."""

    LONG = "COMPRA"
    SHORT = "VENDA"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.LONG else -1

    @property
    def oposta(self) -> "Direction":
        return Direction.SHORT if self is Direction.LONG else Direction.LONG


@dataclass(frozen=True)
class Candle:
    """Um candle OHLCV."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def financeiro(self) -> float:
        """Volume financeiro aproximado do candle (R$)."""
        return self.typical * self.volume


@dataclass
class Series:
    """Serie de candles de um ativo em um timeframe."""

    symbol: str
    timeframe: str
    candles: list[Candle] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.candles)

    def __getitem__(self, item):
        return self.candles[item]

    def __iter__(self):
        return iter(self.candles)

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def volumes(self) -> list[float]:
        return [c.volume for c in self.candles]

    @property
    def last(self) -> Candle:
        return self.candles[-1]

    @property
    def price(self) -> float:
        return self.candles[-1].close

    def tail(self, n: int) -> "Series":
        return Series(self.symbol, self.timeframe, self.candles[-n:])

    def sessions(self) -> list[list[Candle]]:
        """Agrupa os candles por dia de pregao (na ordem cronologica)."""
        grupos: list[list[Candle]] = []
        dia_atual = None
        for c in self.candles:
            dia = c.ts.astimezone(BRT).date()
            if dia != dia_atual:
                grupos.append([])
                dia_atual = dia
            grupos[-1].append(c)
        return grupos

    def sessao_atual(self) -> list[Candle]:
        s = self.sessions()
        return s[-1] if s else []


@dataclass
class Zone:
    """Zona de suporte ou resistencia."""

    low: float
    high: float
    kind: str  # "suporte" | "resistencia"
    touches: int = 1
    strength: float = 0.0  # 0..1
    origem: str = ""

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def distance(self, price: float) -> float:
        if self.contains(price):
            return 0.0
        return self.low - price if price < self.low else price - self.high


@dataclass
class Factor:
    """Um fator de analise avaliado (bloco de confluencia).

    score varia de -1 (fortemente vendedor) a +1 (fortemente comprador).
    """

    nome: str
    score: float
    peso: float
    detalhe: str = ""

    @property
    def contribuicao(self) -> float:
        return self.score * self.peso

    @property
    def direcao(self) -> Optional[Direction]:
        if self.score > 0.15:
            return Direction.LONG
        if self.score < -0.15:
            return Direction.SHORT
        return None


@dataclass
class Trigger:
    """Condicao que precisa acontecer ANTES da entrada."""

    descricao: str
    atendida: Optional[bool] = None  # None = so verificavel em tempo real


@dataclass
class Invalidation:
    """Condicao que cancela a oportunidade (sem virar prejuizo)."""

    descricao: str


@dataclass
class Sizing:
    """Dimensionamento da posicao."""

    quantidade: int
    quantidade_lote: int
    quantidade_fracionario: int
    risco_por_acao: float
    risco_total: float
    financeiro: float
    custo_estimado: float
    limitado_por: str = ""


@dataclass
class BoletaOrdem:
    """Uma linha de ordem para digitar na boleta do Home Broker."""

    momento: str  # "ENTRADA" | "STOP" | "ALVO"
    tipo: str  # "Compra" | "Compra Stop" | "Venda" | "Venda Stop"
    quantidade: int
    preco_disparo: Optional[float]
    preco_limite: Optional[float]
    validade: str
    observacao: str = ""


@dataclass
class Opportunity:
    """Uma oportunidade de trade completa, pronta para leitura humana."""

    symbol: str
    direcao: Direction
    playbook: str
    entrada: float
    stop: float
    alvo: float
    alvo2: Optional[float]
    preco_atual: float
    score: float  # 0..100
    confluencias: list[Factor]
    contras: list[Factor]
    triggers: list[Trigger]
    invalidacoes: list[Invalidation]
    sizing: Sizing
    boleta: list[BoletaOrdem]
    atr: float
    validade: str
    resumo: str
    liquidez_financeira: float = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def risco_por_acao(self) -> float:
        return abs(self.entrada - self.stop)

    @property
    def retorno_por_acao(self) -> float:
        return abs(self.alvo - self.entrada)

    @property
    def rr(self) -> float:
        r = self.risco_por_acao
        return self.retorno_por_acao / r if r > 0 else 0.0

    @property
    def distancia_entrada_pct(self) -> float:
        if self.preco_atual <= 0:
            return 0.0
        return (self.entrada - self.preco_atual) / self.preco_atual * 100.0


@dataclass
class Verdict:
    """Resultado final da varredura."""

    gerado_em: datetime
    oportunidades: list[Opportunity]
    descartados: list[tuple[str, str]]  # (symbol, motivo)
    mercado: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def tem_operacao(self) -> bool:
        return bool(self.oportunidades)


# ---------------------------------------------------------------------------
# utilidades de preco
# ---------------------------------------------------------------------------


def arredonda_tick(preco: float, tick: float = TICK_ACAO, modo: str = "nearest") -> float:
    """Arredonda um preco para o tick da B3 (R$ 0,01 para acoes)."""
    if tick <= 0:
        return preco
    q = preco / tick
    if modo == "up":
        n = math.ceil(q - 1e-9)
    elif modo == "down":
        n = math.floor(q + 1e-9)
    else:
        n = math.floor(q + 0.5)
    return round(n * tick, 10)


def formata_preco(preco: Optional[float]) -> str:
    if preco is None:
        return "-"
    return f"{preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formata_dinheiro(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return "R$ " + formata_preco(v)


def media(vals: Iterable[float]) -> float:
    vals = list(vals)
    return sum(vals) / len(vals) if vals else 0.0


def dentro_do_pregao(ts: datetime, abertura: time = time(10, 0), fechamento: time = time(17, 55)) -> bool:
    t = ts.astimezone(BRT)
    if t.weekday() >= 5:
        return False
    return abertura <= t.time() <= fechamento


def ultimo_valor(seq: Sequence[Optional[float]], offset: int = 0) -> Optional[float]:
    """Ultimo valor nao-nulo de uma serie de indicador (offset=1 -> penultimo)."""
    idx = len(seq) - 1 - offset
    if idx < 0:
        return None
    return seq[idx]
