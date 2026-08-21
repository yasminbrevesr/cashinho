"""Limites de risco - a unica fonte de verdade sobre quanto pode ser arriscado.

Nada aqui sabe o que e' uma estrategia, um setup ou um indicador. O Risk
Manager recebe entrada e stop, aplica os limites e decide. E' de proposito:
risco nao pode depender de quem esta pedindo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional


class ConfiguracaoInvalidaError(ValueError):
    """Limite de risco impossivel de respeitar."""


@dataclass(frozen=True)
class RiskConfig:
    """Todos os limites, em um lugar so."""

    # --- capital e risco por operacao ---------------------------------
    capital: float = 10_000.0
    risco_por_trade_pct: float = 1.0
    risco_max_monetario: Optional[float] = None  # teto absoluto em R$ por trade

    # --- exposicao -----------------------------------------------------
    exposicao_max_por_ativo_pct: float = 20.0
    exposicao_max_total_pct: float = 60.0

    # --- limites do dia -------------------------------------------------
    perda_max_diaria_pct: float = 3.0
    perda_max_diaria_valor: Optional[float] = None  # teto absoluto, se quiser
    max_trades_dia: int = 5
    max_perdas_consecutivas: int = 3

    # --- protecao de longo prazo -----------------------------------------
    drawdown_max_pct: float = 10.0

    # --- execucao ---------------------------------------------------------
    lote: int = 100  # lote padrao da B3
    permitir_fracionario: bool = True
    permitir_piramide: bool = False
    custo_por_trade: float = 0.0

    def __post_init__(self) -> None:
        def positivo(nome: str, valor: float, maximo: Optional[float] = None) -> None:
            if valor is None or valor <= 0:
                raise ConfiguracaoInvalidaError(f"{nome} precisa ser maior que zero (recebido: {valor})")
            if maximo is not None and valor > maximo:
                raise ConfiguracaoInvalidaError(f"{nome} nao pode passar de {maximo} (recebido: {valor})")

        positivo("capital", self.capital)
        positivo("risco_por_trade_pct", self.risco_por_trade_pct, 100.0)
        positivo("exposicao_max_por_ativo_pct", self.exposicao_max_por_ativo_pct, 100.0)
        positivo("exposicao_max_total_pct", self.exposicao_max_total_pct, 100.0)
        positivo("perda_max_diaria_pct", self.perda_max_diaria_pct, 100.0)
        positivo("drawdown_max_pct", self.drawdown_max_pct, 100.0)

        if self.risco_max_monetario is not None and self.risco_max_monetario <= 0:
            raise ConfiguracaoInvalidaError("risco_max_monetario precisa ser maior que zero ou None")
        if self.perda_max_diaria_valor is not None and self.perda_max_diaria_valor <= 0:
            raise ConfiguracaoInvalidaError("perda_max_diaria_valor precisa ser maior que zero ou None")
        if self.max_trades_dia < 1:
            raise ConfiguracaoInvalidaError("max_trades_dia precisa ser pelo menos 1")
        if self.max_perdas_consecutivas < 1:
            raise ConfiguracaoInvalidaError("max_perdas_consecutivas precisa ser pelo menos 1")
        if self.lote < 1:
            raise ConfiguracaoInvalidaError("lote precisa ser pelo menos 1")
        if self.custo_por_trade < 0:
            raise ConfiguracaoInvalidaError("custo_por_trade nao pode ser negativo")
        if self.exposicao_max_por_ativo_pct > self.exposicao_max_total_pct:
            raise ConfiguracaoInvalidaError(
                "exposicao_max_por_ativo_pct nao pode ser maior que exposicao_max_total_pct"
            )

    # ------------------------------------------------------------------
    # limites derivados
    # ------------------------------------------------------------------
    def risco_alvo(self, capital: Optional[float] = None) -> float:
        """Risco monetario por operacao: capital x percentual, respeitando o teto."""
        base = capital if capital is not None else self.capital
        alvo = base * self.risco_por_trade_pct / 100.0
        if self.risco_max_monetario is not None:
            alvo = min(alvo, self.risco_max_monetario)
        return alvo

    def perda_max_diaria(self, capital: Optional[float] = None) -> float:
        base = capital if capital is not None else self.capital
        limite = base * self.perda_max_diaria_pct / 100.0
        if self.perda_max_diaria_valor is not None:
            limite = min(limite, self.perda_max_diaria_valor)
        return limite

    def teto_exposicao_ativo(self, capital: Optional[float] = None) -> float:
        base = capital if capital is not None else self.capital
        return base * self.exposicao_max_por_ativo_pct / 100.0

    def teto_exposicao_total(self, capital: Optional[float] = None) -> float:
        base = capital if capital is not None else self.capital
        return base * self.exposicao_max_total_pct / 100.0

    def drawdown_max(self, pico: float) -> float:
        return pico * self.drawdown_max_pct / 100.0

    # ------------------------------------------------------------------
    # persistencia
    # ------------------------------------------------------------------
    def atualizar(self, **campos: Any) -> "RiskConfig":
        """Nova configuracao com os campos trocados (validada de novo)."""
        desconhecidos = set(campos) - set(asdict(self))
        if desconhecidos:
            raise ConfiguracaoInvalidaError(f"campos desconhecidos: {', '.join(sorted(desconhecidos))}")
        return replace(self, **campos)

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: Mapping[str, Any]) -> "RiskConfig":
        conhecidos = set(asdict(cls()))
        return cls(**{k: v for k, v in dados.items() if k in conhecidos})

    def salvar(self, caminho: str | Path) -> Path:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(self.para_dict(), indent=2, ensure_ascii=False))
        return destino

    @classmethod
    def carregar(cls, caminho: str | Path) -> "RiskConfig":
        origem = Path(caminho)
        if not origem.exists():
            return cls()
        return cls.de_dict(json.loads(origem.read_text()))


PADRAO = RiskConfig()
