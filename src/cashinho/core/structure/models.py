"""Modelos da estrutura de mercado.

Vocabulario objetivo, sem espaco para interpretacao:

- **pivo**: extremo local confirmado por N candles de cada lado (fractal cru);
- **swing high / swing low**: pivo que sobreviveu ao filtro de significancia
  (amplitude minima em ATR) - e' o pivo que realmente move a estrutura;
- **topo / fundo**: o swing high e o swing low mais recentes, os que definem a
  leitura atual;
- **perna (swing)**: o trecho entre dois swings alternados;
- **swing valido**: a perna que serve de base para o Fibonacci.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class TipoPivo(str, Enum):
    TOPO = "topo"
    FUNDO = "fundo"

    @property
    def oposto(self) -> "TipoPivo":
        return TipoPivo.FUNDO if self is TipoPivo.TOPO else TipoPivo.TOPO


class Regime(str, Enum):
    ALTA = "tendencia de alta"
    BAIXA = "tendencia de baixa"
    LATERAL = "lateralizacao"


class TipoEvento(str, Enum):
    ROMPIMENTO = "rompimento"
    POSSIVEL_FALSO_ROMPIMENTO = "possivel falso rompimento"
    PULLBACK = "pullback"
    TESTE = "teste de nivel"


@dataclass(frozen=True)
class Pivot:
    """Extremo local confirmado.

    ``indice_confirmacao`` e' o candle a partir do qual o pivo pode ser usado:
    um pivo com 2 candles de confirmacao a direita so existe 2 candles depois
    de ter acontecido. Usar antes disso seria ler o futuro.
    """

    indice: int
    ts: datetime
    preco: float
    tipo: TipoPivo
    indice_confirmacao: int
    ts_confirmacao: datetime
    proeminencia_atr: float = 0.0
    significativo: bool = False

    @property
    def eh_topo(self) -> bool:
        return self.tipo is TipoPivo.TOPO

    @property
    def eh_fundo(self) -> bool:
        return self.tipo is TipoPivo.FUNDO

    def confirmado_em(self, indice: int) -> bool:
        return indice >= self.indice_confirmacao


@dataclass(frozen=True)
class Swing:
    """Perna entre dois swings alternados."""

    inicio: Pivot
    fim: Pivot
    amplitude: float
    amplitude_atr: float
    amplitude_pct: float
    duracao: int
    valido: bool
    motivo: str = ""

    @property
    def direcao(self) -> Direction:
        return Direction.LONG if self.fim.preco > self.inicio.preco else Direction.SHORT

    @property
    def eh_alta(self) -> bool:
        return self.direcao is Direction.LONG

    def retracao_em(self, preco: float) -> Optional[float]:
        """Quanto da perna ja foi devolvido (0 = extremo, 1 = origem)."""
        if self.amplitude == 0:
            return None
        return abs(self.fim.preco - preco) / self.amplitude


@dataclass(frozen=True)
class Level:
    """Zona de suporte ou resistencia formada por pivos empilhados."""

    low: float
    high: float
    tipo: str  # "suporte" | "resistencia"
    toques: int
    forca: float  # 0..1
    ultimo_toque: datetime
    pivos: tuple[int, ...] = ()
    origem: str = "pivos"

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    def contem(self, preco: float) -> bool:
        return self.low <= preco <= self.high

    def distancia(self, preco: float) -> float:
        if self.contem(preco):
            return 0.0
        return self.low - preco if preco < self.low else preco - self.high

    def distancia_pct(self, preco: float) -> float:
        return self.distancia(preco) / preco * 100.0 if preco else 0.0


@dataclass(frozen=True)
class FibLevel:
    razao: float
    rotulo: str
    preco: float
    tipo: str  # "retracao" | "extensao"
    confluencia: Optional[Level] = None

    @property
    def tem_confluencia(self) -> bool:
        return self.confluencia is not None


@dataclass(frozen=True)
class FibZone:
    """Faixa de precos entre duas razoes de Fibonacci."""

    nome: str
    low: float
    high: float
    razao_inicio: float
    razao_fim: float
    descricao: str = ""

    def contem(self, preco: float) -> bool:
        return self.low <= preco <= self.high


@dataclass(frozen=True)
class FibGrid:
    """Grade de Fibonacci ancorada em um swing valido.

    So e' criada quando o algoritmo encontra uma perna valida - nunca
    desenhada a esmo.
    """

    swing: Swing
    ancora_0: float  # extremo da perna (100% recuperado)
    ancora_100: float  # origem da perna
    retracoes: tuple[FibLevel, ...]
    extensoes: tuple[FibLevel, ...]
    zonas: tuple[FibZone, ...]

    @property
    def direcao(self) -> Direction:
        return self.swing.direcao

    def nivel(self, razao: float) -> Optional[FibLevel]:
        for n in self.retracoes + self.extensoes:
            if abs(n.razao - razao) < 1e-9:
                return n
        return None

    def zona_do_preco(self, preco: float) -> Optional[FibZone]:
        for z in self.zonas:
            if z.contem(preco):
                return z
        return None

    def confluencias(self) -> tuple[FibLevel, ...]:
        return tuple(n for n in self.retracoes + self.extensoes if n.tem_confluencia)


@dataclass(frozen=True)
class EventoEstrutura:
    tipo: TipoEvento
    direcao: Direction
    ts: datetime
    indice: int
    preco: float
    forca: float  # 0..1
    descricao: str
    nivel: Optional[Level] = None
    detalhes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Tendencia:
    regime: Regime
    forca: float  # 0..1
    sequencia: str  # "HH/HL", "LH/LL", "HH/LL", ...
    descricao: str
    topos: tuple[Pivot, ...] = ()
    fundos: tuple[Pivot, ...] = ()
    range_low: Optional[float] = None
    range_high: Optional[float] = None

    @property
    def direcao(self) -> Optional[Direction]:
        if self.regime is Regime.ALTA:
            return Direction.LONG
        if self.regime is Regime.BAIXA:
            return Direction.SHORT
        return None


@dataclass
class MarketStructure:
    """Leitura completa da estrutura em um instante."""

    symbol: str
    timeframe: str
    ts: datetime
    preco: float
    atr: float
    pivos: list[Pivot]
    swing_highs: list[Pivot]
    swing_lows: list[Pivot]
    swings: list[Swing]
    tendencia: Tendencia
    suportes: list[Level]
    resistencias: list[Level]
    eventos: list[EventoEstrutura]
    swing_valido: Optional[Swing] = None
    fib: Optional[FibGrid] = None
    motivo_sem_fib: str = ""
    zona_atual: Optional[Level] = None

    # -- atalhos de leitura ------------------------------------------------
    @property
    def topo(self) -> Optional[Pivot]:
        """Swing high mais recente."""
        return self.swing_highs[-1] if self.swing_highs else None

    @property
    def fundo(self) -> Optional[Pivot]:
        """Swing low mais recente."""
        return self.swing_lows[-1] if self.swing_lows else None

    @property
    def suporte(self) -> Optional[Level]:
        """Suporte mais proximo abaixo do preco."""
        return self.suportes[0] if self.suportes else None

    @property
    def resistencia(self) -> Optional[Level]:
        """Resistencia mais proxima acima do preco."""
        return self.resistencias[0] if self.resistencias else None

    def eventos_do_tipo(self, tipo: TipoEvento) -> list[EventoEstrutura]:
        return [e for e in self.eventos if e.tipo is tipo]

    @property
    def rompimento(self) -> Optional[EventoEstrutura]:
        eventos = self.eventos_do_tipo(TipoEvento.ROMPIMENTO)
        return eventos[-1] if eventos else None

    @property
    def falso_rompimento(self) -> Optional[EventoEstrutura]:
        eventos = self.eventos_do_tipo(TipoEvento.POSSIVEL_FALSO_ROMPIMENTO)
        return eventos[-1] if eventos else None

    @property
    def pullback(self) -> Optional[EventoEstrutura]:
        eventos = self.eventos_do_tipo(TipoEvento.PULLBACK)
        return eventos[-1] if eventos else None

    def para_dict(self) -> dict:
        """Payload serializavel - o que uma interface grafica consome."""

        def _pivo(p: Pivot) -> dict:
            return {
                "indice": p.indice,
                "ts": p.ts.isoformat(),
                "preco": round(p.preco, 4),
                "tipo": p.tipo.value,
                "confirmado_em": p.ts_confirmacao.isoformat(),
                "significativo": p.significativo,
            }

        def _nivel(l: Level) -> dict:
            return {
                "low": round(l.low, 4),
                "high": round(l.high, 4),
                "tipo": l.tipo,
                "toques": l.toques,
                "forca": round(l.forca, 3),
                "ultimo_toque": l.ultimo_toque.isoformat(),
            }

        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "ts": self.ts.isoformat(),
            "preco": round(self.preco, 4),
            "atr": round(self.atr, 4),
            "tendencia": {
                "regime": self.tendencia.regime.value,
                "forca": round(self.tendencia.forca, 3),
                "sequencia": self.tendencia.sequencia,
                "descricao": self.tendencia.descricao,
            },
            "pivos": [_pivo(p) for p in self.pivos],
            "swing_highs": [_pivo(p) for p in self.swing_highs],
            "swing_lows": [_pivo(p) for p in self.swing_lows],
            "suportes": [_nivel(l) for l in self.suportes],
            "resistencias": [_nivel(l) for l in self.resistencias],
            "eventos": [
                {
                    "tipo": e.tipo.value,
                    "direcao": e.direcao.value,
                    "ts": e.ts.isoformat(),
                    "preco": round(e.preco, 4),
                    "forca": round(e.forca, 3),
                    "descricao": e.descricao,
                }
                for e in self.eventos
            ],
            "fibonacci": None
            if self.fib is None
            else {
                "motivo": "swing valido identificado",
                "direcao": self.fib.direcao.value,
                "ancora_0": round(self.fib.ancora_0, 4),
                "ancora_100": round(self.fib.ancora_100, 4),
                "swing": {
                    "inicio": self.fib.swing.inicio.ts.isoformat(),
                    "fim": self.fib.swing.fim.ts.isoformat(),
                    "amplitude_atr": round(self.fib.swing.amplitude_atr, 2),
                },
                "retracoes": [
                    {"razao": n.razao, "rotulo": n.rotulo, "preco": round(n.preco, 4),
                     "confluencia": n.tem_confluencia}
                    for n in self.fib.retracoes
                ],
                "extensoes": [
                    {"razao": n.razao, "rotulo": n.rotulo, "preco": round(n.preco, 4),
                     "confluencia": n.tem_confluencia}
                    for n in self.fib.extensoes
                ],
                "zonas": [
                    {"nome": z.nome, "low": round(z.low, 4), "high": round(z.high, 4),
                     "descricao": z.descricao}
                    for z in self.fib.zonas
                ],
            },
            "motivo_sem_fib": self.motivo_sem_fib,
        }
