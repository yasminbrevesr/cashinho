"""Confianca: quantas observacoes sustentam o que o score esta dizendo.

Uma operacao de +4R nao vence trinta operacoes de +0,45R de expectancia. O
primeiro numero e' sorte ate prova em contrario; o segundo e' evidencia. Este
arquivo e' o que impede o Advisor de confundir os dois.

A confianca cai por tres motivos, e cada um aparece na saida:
  - poucos candles para medir;
  - poucas operacoes no historico (ou nenhum historico);
  - componentes indisponiveis na fonte de dados atual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

# operacoes a partir das quais a evidencia estatistica vale integralmente
AMOSTRA_PLENA = 30
AMOSTRA_MINIMA = 5
CANDLES_PLENOS = 200


class NivelDeConfianca(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"
    INSUFICIENTE = "INSUFICIENTE"

    @property
    def recomenda(self) -> bool:
        """Da para virar recomendacao? INSUFICIENTE nunca vira."""
        return self is not NivelDeConfianca.INSUFICIENTE


@dataclass(frozen=True)
class Estatistica:
    """Historico comparavel de um timeframe - quando existir.

    Nada aqui e' inventado: se o projeto ainda nao tem backtest daquele
    timeframe, ``disponivel`` e' falso e a performance nao entra no score.
    """

    trades: int = 0
    expectancy: Optional[float] = None      # em R por operacao
    profit_factor: Optional[float] = None
    max_drawdown_pct: Optional[float] = None

    @property
    def disponivel(self) -> bool:
        return self.trades > 0 and self.expectancy is not None

    @property
    def peso_da_amostra(self) -> float:
        """0..1 pela raiz do numero de trades - cresce rapido e satura."""
        if self.trades <= 0:
            return 0.0
        return min(math.sqrt(self.trades / AMOSTRA_PLENA), 1.0)

    @property
    def nota(self) -> Optional[float]:
        """Nota de performance **ja descontada pelo tamanho da amostra**.

        E' aqui que uma operacao sortuda perde para trinta medianas: a
        expectancia bruta e' multiplicada pelo peso da amostra.
        """
        if not self.disponivel:
            return None
        # expectancia de +0,5R ja e' boa; satura em 1R
        bruta = max(0.0, min(self.expectancy / 1.0, 1.0)) * 100
        if self.profit_factor is not None:
            bruta = bruta * min(self.profit_factor / 1.5, 1.2)
        return round(min(bruta * self.peso_da_amostra, 100.0), 1)

    @property
    def leitura(self) -> str:
        if not self.disponivel:
            return "sem historico comparavel para este timeframe"
        partes = [f"{self.trades} operacao(oes)",
                  f"expectancy {self.expectancy:+.2f}R"]
        if self.profit_factor is not None:
            partes.append(f"PF {self.profit_factor:.2f}")
        if self.max_drawdown_pct is not None:
            partes.append(f"drawdown {self.max_drawdown_pct:.1f}%")
        if self.trades < AMOSTRA_PLENA:
            partes.append(f"amostra pequena: nota reduzida a "
                          f"{self.peso_da_amostra:.0%}")
        return " · ".join(partes)

    def para_dict(self) -> dict:
        return {
            "trades": self.trades, "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "disponivel": self.disponivel,
            "peso_da_amostra": round(self.peso_da_amostra, 3),
            "nota": self.nota, "leitura": self.leitura,
        }


@dataclass(frozen=True)
class Confianca:
    """O quanto da para confiar nesta recomendacao - com o porque."""

    valor: float                 # 0..100
    nivel: NivelDeConfianca
    motivos: tuple[str, ...] = ()

    @property
    def recomenda(self) -> bool:
        return self.nivel.recomenda

    def para_dict(self) -> dict:
        return {"valor": round(self.valor, 1), "nivel": self.nivel.value,
                "recomenda": self.recomenda, "motivos": list(self.motivos)}


def calcular_confianca(candles: int, estatistica: Optional[Estatistica],
                       indisponiveis: Sequence[str] = (),
                       vantagem: Optional[float] = None) -> Confianca:
    """Junta amostra de candles, amostra de trades e lacunas de dados."""
    motivos: list[str] = []

    # 1. candles para medir
    por_candles = min(candles / CANDLES_PLENOS, 1.0)
    if candles < CANDLES_PLENOS:
        motivos.append(f"{candles} candles fechados (pleno a partir de {CANDLES_PLENOS})")

    # 2. historico de operacoes
    if estatistica is None or not estatistica.disponivel:
        por_trades = 0.35     # sem historico nao zera, mas limita bastante
        motivos.append("sem evidencia estatistica: nenhum historico comparavel")
    else:
        por_trades = estatistica.peso_da_amostra
        if estatistica.trades < AMOSTRA_MINIMA:
            motivos.append(f"apenas {estatistica.trades} operacao(oes) no historico: "
                           "insuficiente para concluir")
        elif estatistica.trades < AMOSTRA_PLENA:
            motivos.append(f"{estatistica.trades} operacoes: amostra ainda pequena")

    # 3. lacunas de dado
    por_dados = 1.0
    if indisponiveis:
        por_dados = max(0.4, 1.0 - 0.15 * len(indisponiveis))
        motivos.append(f"sem dado para: {', '.join(indisponiveis)}")

    # 4. distancia para o segundo colocado
    por_vantagem = 1.0
    if vantagem is not None:
        por_vantagem = min(0.6 + vantagem / 25.0, 1.0)
        if vantagem < 5:
            motivos.append(f"vantagem de apenas {vantagem:.1f} ponto(s) sobre o segundo")

    valor = 100 * por_candles * por_trades * por_dados * por_vantagem
    return Confianca(valor, _nivel(valor, candles, estatistica), tuple(motivos))


def _nivel(valor: float, candles: int, estatistica: Optional[Estatistica]) -> NivelDeConfianca:
    if candles < 30:
        return NivelDeConfianca.INSUFICIENTE
    if valor >= 60:
        return NivelDeConfianca.ALTA
    if valor >= 35:
        return NivelDeConfianca.MEDIA
    if valor >= 15:
        return NivelDeConfianca.BAIXA
    return NivelDeConfianca.INSUFICIENTE
