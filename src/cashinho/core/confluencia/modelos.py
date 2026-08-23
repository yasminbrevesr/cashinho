"""Modelos das quatro camadas e da Opportunity que nasce da confluencia."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Union

from ...models import Direction
from .estados import ContextState, SetupState, TrendState, TriggerState, Vies

Estado = Union[ContextState, TrendState, SetupState, TriggerState]


@dataclass(frozen=True)
class Camada:
    """Leitura de UMA camada, com a marcacao de tempo que a torna auditavel.

    Tres instantes diferentes, e a confusao entre eles e' a origem de quase
    todo vazamento entre timeframes:

    - ``ts``: abertura do candle que gerou a leitura;
    - ``fechado_em``: quando esse candle fechou - e' a partir daqui que a
      leitura pode ser usada;
    - ``lido_em``: o instante da consulta.

    ``fechado_em <= lido_em`` sempre. Se algum dia nao for, ha futuro na
    leitura.
    """

    papel: str
    timeframe: str
    estado: Estado
    ts: datetime
    fechado_em: datetime
    lido_em: datetime
    forca: float = 0.0
    razoes: tuple[str, ...] = ()
    detalhes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fechado_em > self.lido_em:
            raise ValueError(
                f"camada {self.papel} ({self.timeframe}): candle fecha em {self.fechado_em} "
                f"mas a leitura e' de {self.lido_em} - isso seria ler o futuro"
            )

    @property
    def vies(self) -> Vies:
        estado = self.estado
        if isinstance(estado, (ContextState, TrendState)):
            return estado.vies
        return Vies(self.detalhes.get("vies", Vies.NEUTRAL.value))

    @property
    def idade(self) -> timedelta:
        """Ha quanto tempo esta leitura esta valendo."""
        return self.lido_em - self.fechado_em

    @property
    def idade_minutos(self) -> float:
        return self.idade.total_seconds() / 60.0

    @property
    def valor(self) -> str:
        return self.estado.value

    def para_dict(self) -> dict:
        return {
            "papel": self.papel,
            "timeframe": self.timeframe,
            "estado": self.valor,
            "vies": self.vies.value,
            "ts": self.ts.isoformat(),
            "fechado_em": self.fechado_em.isoformat(),
            "idade_minutos": round(self.idade_minutos, 1),
            "forca": round(self.forca, 3),
            "razoes": list(self.razoes),
        }


# As quatro camadas sao tipos distintos, e nao strings soltas: assim uma
# regra que pede Setup nao aceita um Trigger por engano. O papel e' fixado
# pela classe (``PAPEL``), nao pelo chamador.


@dataclass(frozen=True)
class Context(Camada):
    """Camada de contexto - o timeframe mais alto da configuracao."""

    PAPEL = "context"

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", self.PAPEL)
        super().__post_init__()

    @property
    def bullish(self) -> bool:
        return self.estado is ContextState.BULLISH

    @property
    def bearish(self) -> bool:
        return self.estado is ContextState.BEARISH


@dataclass(frozen=True)
class Trend(Camada):
    """Camada de tendencia - a direcao dominante no timeframe intermediario."""

    PAPEL = "trend"

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", self.PAPEL)
        super().__post_init__()

    @property
    def definida(self) -> bool:
        return self.estado is not TrendState.SIDEWAYS


@dataclass(frozen=True)
class Setup(Camada):
    """Camada de setup - a formacao no timeframe de operacao."""

    PAPEL = "setup"

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", self.PAPEL)
        super().__post_init__()

    @property
    def existe(self) -> bool:
        return self.estado.existe


@dataclass(frozen=True)
class Trigger(Camada):
    """Camada de gatilho - o que o ultimo candle fechado fez."""

    PAPEL = "trigger"

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", self.PAPEL)
        super().__post_init__()

    @property
    def disparou(self) -> bool:
        return self.estado.existe


@dataclass(frozen=True)
class LeituraMultiTimeframe:
    """As quatro camadas lidas no MESMO instante."""

    symbol: str
    instante: datetime
    camadas: tuple[Camada, ...]
    faltando: tuple[str, ...] = ()  # papeis sem candle fechado ainda
    avisos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for c in self.camadas:
            if c.lido_em != self.instante:
                raise ValueError(
                    f"camada {c.papel} lida em {c.lido_em}, mas a leitura e' de "
                    f"{self.instante} - as camadas precisam ser do mesmo instante"
                )

    def camada(self, papel: str) -> Optional[Camada]:
        for c in self.camadas:
            if c.papel == papel:
                return c
        return None

    @property
    def context(self) -> Optional[Context]:
        return self.camada("context")  # type: ignore[return-value]

    @property
    def trend(self) -> Optional[Trend]:
        return self.camada("trend")  # type: ignore[return-value]

    @property
    def setup(self) -> Optional[Setup]:
        return self.camada("setup")  # type: ignore[return-value]

    @property
    def trigger(self) -> Optional[Trigger]:
        return self.camada("trigger")  # type: ignore[return-value]

    @property
    def completa(self) -> bool:
        return not self.faltando

    def vies_alinhado(self) -> Optional[Vies]:
        """O vies comum a todas as camadas direcionais, se houver um so."""
        vieses = {c.vies for c in self.camadas if c.vies is not Vies.NEUTRAL}
        if len(vieses) == 1:
            return next(iter(vieses))
        return None

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "instante": self.instante.isoformat(),
            "completa": self.completa,
            "faltando": list(self.faltando),
            "vies_alinhado": self.vies_alinhado().value if self.vies_alinhado() else None,
            "camadas": [c.para_dict() for c in self.camadas],
            "avisos": list(self.avisos),
        }


@dataclass(frozen=True)
class Opportunity:
    """So nasce quando uma regra configurada e' inteiramente satisfeita.

    Nao e' ordem: nao tem quantidade. Os niveis sao referencias para o Risk
    Manager dimensionar - e ele continua podendo dizer nao.
    """

    symbol: str
    instante: datetime
    direcao: Direction
    regra: str
    leitura: LeituraMultiTimeframe
    confianca: float
    razoes: tuple[str, ...]
    invalidacao: str
    niveis: dict = field(default_factory=dict)

    @property
    def resumo_das_camadas(self) -> str:
        return " · ".join(f"{c.timeframe}: {c.valor}" for c in self.leitura.camadas)

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "instante": self.instante.isoformat(),
            "direcao": self.direcao.value,
            "regra": self.regra,
            "confianca": round(self.confianca, 3),
            "razoes": list(self.razoes),
            "invalidacao": self.invalidacao,
            "niveis": {k: round(v, 4) for k, v in self.niveis.items()},
            "leitura": self.leitura.para_dict(),
        }
