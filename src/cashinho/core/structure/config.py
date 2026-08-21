"""Parametros da leitura de estrutura - nada de numero magico espalhado."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EstruturaConfig:
    """Limiares objetivos usados para identificar a estrutura.

    Todos sao normalizados por ATR (ou por % do preco) para que o mesmo
    ajuste funcione em PETR4 a R$ 38 e em ITUB4 a R$ 32.
    """

    # --- pivos -------------------------------------------------------
    pivo_esquerda: int = 2
    pivo_direita: int = 2
    atr_periodo: int = 14

    # --- significancia do swing --------------------------------------
    swing_min_atr: float = 1.0
    swing_min_pct: float = 0.15

    # --- suporte e resistencia ---------------------------------------
    tolerancia_nivel_atr: float = 0.35
    max_niveis_por_lado: int = 4
    lookback_niveis: int = 200

    # --- eventos ------------------------------------------------------
    janela_eventos: int = 6
    rompimento_min_atr: float = 0.10
    rompimento_volume_min: float = 1.2
    falso_rompimento_janela: int = 3
    pullback_min: float = 0.236
    pullback_max: float = 0.786

    # --- fibonacci -----------------------------------------------------
    retracoes: tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786)
    extensoes: tuple[float, ...] = (1.272, 1.618)
    fib_confluencia_atr: float = 0.30

    # --- lateralizacao --------------------------------------------------
    lateral_max_atr: float = 3.0
    tolerancia_estrutura_atr: float = 0.15

    def __post_init__(self) -> None:
        if self.pivo_esquerda < 1 or self.pivo_direita < 1:
            raise ValueError("pivo_esquerda e pivo_direita precisam ser >= 1")
        if self.swing_min_atr < 0 or self.swing_min_pct < 0:
            raise ValueError("limiares de swing nao podem ser negativos")
        if not self.retracoes:
            raise ValueError("configure ao menos uma razao de retracao")


PADRAO = EstruturaConfig()
"""Ajuste padrao, calibrado para graficos de 5m/15m de acoes liquidas."""
