"""Contrato de saida de uma estrategia: o objeto ``Signal``.

Uma estrategia NAO envia ordem, nao dimensiona posicao e nao conversa com o
Risk Manager. Ela olha os dados e descreve uma condicao: qual e' a leitura,
quanta confianca ela tem, por que, e o que invalidaria essa leitura. Quem
decide tamanho e' o risco; quem decide executar e' voce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class Action(str, Enum):
    """Os quatro estados possiveis de um sinal."""

    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    NONE = "NONE"

    @property
    def acionavel(self) -> bool:
        """BUY e SELL pedem uma decisao agora; WAIT e NONE, nao."""
        return self in (Action.BUY, Action.SELL)

    @property
    def direcao(self) -> Optional[Direction]:
        if self is Action.BUY:
            return Direction.LONG
        if self is Action.SELL:
            return Direction.SHORT
        return None

    @property
    def descricao(self) -> str:
        return {
            Action.BUY: "condicao de compra identificada",
            Action.SELL: "condicao de venda identificada",
            Action.WAIT: "ha vies, mas falta confirmacao - acompanhar",
            Action.NONE: "nada a fazer neste ativo agora",
        }[self]


@dataclass(frozen=True)
class Factor:
    """Um fator avaliado pela estrategia, a favor ou contra a leitura.

    ``favoravel`` e' relativo ao vies que a estrategia esta avaliando: em um
    vies de alta, "volume acima da media" e' favoravel; o mesmo fator seria
    favoravel em um vies de baixa. ``None`` marca fator neutro.
    """

    nome: str
    favoravel: Optional[bool]
    detalhe: str
    peso: float = 1.0
    obrigatorio: bool = False

    @property
    def contrario(self) -> bool:
        return self.favoravel is False

    @property
    def neutro(self) -> bool:
        return self.favoravel is None

    @property
    def simbolo(self) -> str:
        return {True: "✔", False: "✖", None: "·"}[self.favoravel]


@dataclass(frozen=True)
class Signal:
    """O que uma estrategia produz. Sempre - inclusive quando nao ha nada."""

    symbol: str
    timestamp: datetime
    timeframe: str
    action: Action
    setup: str
    confidence: float  # 0..1
    reasons: tuple[str, ...]
    invalidation: str

    # contexto da leitura
    strategy: str = ""
    vies: Optional[Direction] = None
    factors: tuple[Factor, ...] = ()
    niveis: dict = field(default_factory=dict)  # precos de REFERENCIA, nao ordens
    experimental: bool = True
    aviso: str = ""
    # payload livre para quem produz o sinal anexar contexto extra (a leitura
    # multi-timeframe, por exemplo). Nao entra no para_dict: nao ha garantia
    # de que o conteudo seja serializavel.
    extras: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence precisa ficar entre 0 e 1 (recebido: {self.confidence})")
        if self.action.acionavel and not self.reasons:
            raise ValueError("um sinal acionavel precisa dizer por que")

    # -- leitura dos fatores --------------------------------------------
    @property
    def favoraveis(self) -> tuple[Factor, ...]:
        return tuple(f for f in self.factors if f.favoravel is True)

    @property
    def contrarios(self) -> tuple[Factor, ...]:
        return tuple(f for f in self.factors if f.favoravel is False)

    @property
    def neutros(self) -> tuple[Factor, ...]:
        return tuple(f for f in self.factors if f.favoravel is None)

    @property
    def faltando(self) -> tuple[Factor, ...]:
        """Condicoes obrigatorias ainda nao atendidas - o que segura um WAIT."""
        return tuple(f for f in self.contrarios if f.obrigatorio)

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "action": self.action.value,
            "setup": self.setup,
            "confidence": round(self.confidence, 3),
            "reasons": list(self.reasons),
            "invalidation": self.invalidation,
            "strategy": self.strategy,
            "vies": self.vies.value if self.vies else None,
            "experimental": self.experimental,
            "aviso": self.aviso,
            "factors": [
                {
                    "nome": f.nome,
                    "favoravel": f.favoravel,
                    "detalhe": f.detalhe,
                    "peso": f.peso,
                    "obrigatorio": f.obrigatorio,
                }
                for f in self.factors
            ],
            "niveis": {k: round(v, 4) for k, v in self.niveis.items()},
        }
