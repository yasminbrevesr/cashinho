"""Configuracao do Scanner B3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

WATCHLIST_PADRAO: tuple[str, ...] = (
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3",
    "ABEV3", "BBAS3", "WEGE3", "PRIO3", "RENT3",
)
"""Acoes liquidas da B3 - ponto de partida, nao recomendacao."""

ORDENACOES = ("score", "rr", "risco", "ativo", "status")


class ConfiguracaoInvalidaError(ValueError):
    """Configuracao de scanner impossivel de usar."""


@dataclass(frozen=True)
class ScannerConfig:
    """O que varrer, com que filtros e em que ordem mostrar."""

    watchlist: tuple[str, ...] = WATCHLIST_PADRAO
    timeframe_base: str = "1m"
    dias: int = 5

    # --- filtros iniciais (baratos, rodam antes do pipeline) ----------
    liquidez_minima_diaria: float = 5_000_000.0  # R$ negociados por pregao
    volume_relativo_minimo: float = 0.5  # movimento de agora vs a media do ativo
    candles_minimos: int = 120
    atraso_maximo_minutos: Optional[float] = None  # None = nao checa defasagem
    atr_min_pct: float = 0.15
    atr_max_pct: float = 3.0
    spread_maximo_ticks: float = 3.0

    # --- saida ---------------------------------------------------------
    ordenar_por: str = "score"
    apenas_operaveis: bool = False  # so o que pode virar ordem
    max_resultados: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.watchlist:
            raise ConfiguracaoInvalidaError("a watchlist nao pode ficar vazia")
        if self.ordenar_por not in ORDENACOES:
            raise ConfiguracaoInvalidaError(
                f"ordenacao invalida: {self.ordenar_por!r} (use {', '.join(ORDENACOES)})"
            )
        if self.dias < 1:
            raise ConfiguracaoInvalidaError("dias precisa ser pelo menos 1")
        if self.candles_minimos < 1:
            raise ConfiguracaoInvalidaError("candles_minimos precisa ser pelo menos 1")
        if self.atr_min_pct >= self.atr_max_pct:
            raise ConfiguracaoInvalidaError("atr_min_pct precisa ser menor que atr_max_pct")
        object.__setattr__(self, "watchlist", tuple(
            dict.fromkeys(a.strip().upper() for a in self.watchlist if a.strip())
        ))

    def com_watchlist(self, ativos) -> "ScannerConfig":
        from dataclasses import replace

        return replace(self, watchlist=tuple(ativos))
