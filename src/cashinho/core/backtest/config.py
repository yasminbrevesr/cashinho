"""Configuracao de uma rodada de backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Optional

from ..mtf.session import SESSAO_B3, Sessao
from ..risk.config import RiskConfig
from .costs import ModeloCustos


@dataclass(frozen=True)
class BacktestConfig:
    """Tudo o que define a rodada - nada fica implicito no codigo do engine."""

    # --- ativo e janela ------------------------------------------------
    symbol: str = ""
    timeframe_base: str = "1m"  # onde a execucao acontece
    timeframe_setup: str = "5m"  # onde a estrategia decide
    inicio: Optional[date] = None
    fim: Optional[date] = None

    # --- capital e risco -----------------------------------------------
    capital_inicial: float = 100_000.0
    risco: RiskConfig = field(default_factory=RiskConfig)

    # --- custos ----------------------------------------------------------
    custos: ModeloCustos = field(default_factory=ModeloCustos)

    # --- horario ----------------------------------------------------------
    sessao: Sessao = SESSAO_B3
    entrada_ate: Optional[time] = time(16, 30)  # sem entradas novas depois disso
    fechar_em: Optional[time] = time(17, 40)  # zera a posicao (day trade)

    # --- regras de execucao -------------------------------------------------
    janela_maxima: Optional[int] = 400  # candles entregues a estrategia por avaliacao
    prioridade_intracandle: str = "stop"  # "stop" | "alvo" | "nenhuma"
    sair_no_sinal_contrario: bool = False
    permitir_venda: bool = True

    def __post_init__(self) -> None:
        if self.capital_inicial <= 0:
            raise ValueError("capital_inicial precisa ser maior que zero")
        if self.prioridade_intracandle not in ("stop", "alvo", "nenhuma"):
            raise ValueError(
                f"prioridade_intracandle invalida: {self.prioridade_intracandle!r} "
                "(use 'stop', 'alvo' ou 'nenhuma')"
            )
        if self.inicio and self.fim and self.inicio > self.fim:
            raise ValueError("inicio depois do fim")
        if self.janela_maxima is not None and self.janela_maxima < 2:
            raise ValueError("janela_maxima precisa ser pelo menos 2 candles (ou None)")
        # o capital do backtest manda no capital do risco
        if self.risco.capital != self.capital_inicial:
            object.__setattr__(self, "risco", self.risco.atualizar(capital=self.capital_inicial))

    def dentro_do_periodo(self, dia: date) -> bool:
        if self.inicio and dia < self.inicio:
            return False
        if self.fim and dia > self.fim:
            return False
        return True
