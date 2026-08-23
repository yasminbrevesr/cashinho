"""Walk-forward: a mesma pergunta, repetida ao longo do tempo.

Uma divisao unica responde "funcionou naquele pedaco?". O walk-forward
responde algo mais util: "funcionou repetidamente, em pedacos diferentes?".
A serie e' cortada em janelas que andam para a frente - treina num trecho,
mede no seguinte, avanca - e o que interessa nao e' o melhor ciclo: e'
**quantos** ciclos se sustentaram.

Suporte inicial, de proposito: janela fixa, passo fixo, sem otimizacao dentro
de cada ciclo alem da comparacao de poucos candidatos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence

from ...models import Series
from ..backtest.config import BacktestConfig
from .divisao import DivisaoInvalidaError, Janela, Particao, dias_da_serie
from .relatorio import Medidas
from .validador import ValidadorDeEstrategia


@dataclass(frozen=True)
class ConfigWalkForward:
    """O tamanho das janelas, em pregoes."""

    dias_de_treino: int = 10
    dias_de_teste: int = 5
    passo: Optional[int] = None  # None = anda o tamanho da janela de teste

    def __post_init__(self) -> None:
        if self.dias_de_treino < 1 or self.dias_de_teste < 1:
            raise DivisaoInvalidaError("as janelas precisam ter ao menos um pregao")
        if self.passo is not None and self.passo < 1:
            raise DivisaoInvalidaError("o passo precisa ser de ao menos um pregao")

    @property
    def avanco(self) -> int:
        return self.passo or self.dias_de_teste


@dataclass(frozen=True)
class Ciclo:
    """Um ciclo do walk-forward: treinou aqui, mediu ali."""

    indice: int
    treino: Janela
    teste: Janela
    medida_treino: Medidas
    medida_teste: Medidas

    @property
    def sustentou(self) -> bool:
        """O ciclo se manteve fora da amostra?"""
        return self.medida_teste.retorno_pct > 0 and self.medida_teste.n_trades > 0

    def para_dict(self) -> dict:
        return {
            "ciclo": self.indice,
            "treino": self.treino.para_dict(),
            "teste": self.teste.para_dict(),
            "medida_treino": self.medida_treino.para_dict(),
            "medida_teste": self.medida_teste.para_dict(),
            "sustentou": self.sustentou,
        }


@dataclass
class ResultadoWalkForward:
    """O conjunto de ciclos e o que eles dizem juntos."""

    ciclos: list[Ciclo] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.ciclos)

    @property
    def sustentaram(self) -> int:
        return sum(1 for c in self.ciclos if c.sustentou)

    @property
    def consistencia(self) -> float:
        """Fracao dos ciclos que se sustentaram fora da amostra."""
        return self.sustentaram / self.total if self.total else 0.0

    @property
    def retorno_medio_fora(self) -> float:
        if not self.ciclos:
            return 0.0
        return sum(c.medida_teste.retorno_pct for c in self.ciclos) / self.total

    @property
    def trades_fora(self) -> int:
        return sum(c.medida_teste.n_trades for c in self.ciclos)

    @property
    def veredito(self) -> str:
        if not self.ciclos:
            return "nenhum ciclo pode ser montado com estes dados"
        if self.total < 3:
            return (
                f"apenas {self.total} ciclo(s): poucos para falar em consistencia - "
                "aumente o periodo ou reduza as janelas"
            )
        if self.consistencia >= 0.6:
            return (
                f"{self.sustentaram} de {self.total} ciclos se sustentaram fora da amostra "
                f"({self.consistencia:.0%})"
            )
        return (
            f"so {self.sustentaram} de {self.total} ciclos se sustentaram "
            f"({self.consistencia:.0%}): o desempenho nao se repete"
        )

    def para_dict(self) -> dict:
        return {
            "ciclos": [c.para_dict() for c in self.ciclos],
            "total": self.total,
            "sustentaram": self.sustentaram,
            "consistencia": round(self.consistencia, 3),
            "retorno_medio_fora": round(self.retorno_medio_fora, 3),
            "trades_fora": self.trades_fora,
            "veredito": self.veredito,
            "avisos": list(self.avisos),
        }


def janelas_walk_forward(serie: Series, config: ConfigWalkForward) -> list[tuple[Janela, Janela]]:
    """Monta os pares (treino, teste) andando para a frente."""
    dias = dias_da_serie(serie)
    necessarios = config.dias_de_treino + config.dias_de_teste
    if len(dias) < necessarios:
        raise DivisaoInvalidaError(
            f"a serie tem {len(dias)} pregoes; sao necessarios {necessarios} "
            f"({config.dias_de_treino} de treino + {config.dias_de_teste} de teste)"
        )

    from .divisao import _janela

    pares: list[tuple[Janela, Janela]] = []
    inicio = 0
    while inicio + necessarios <= len(dias):
        treino = dias[inicio: inicio + config.dias_de_treino]
        teste = dias[inicio + config.dias_de_treino: inicio + necessarios]
        pares.append((
            _janela(serie, Particao.TRAIN, treino),
            _janela(serie, Particao.VALIDATION, teste),  # fora da amostra do ciclo
        ))
        inicio += config.avanco
    return pares


def walk_forward(
    validador: ValidadorDeEstrategia,
    serie: Series,
    config: Optional[ConfigWalkForward] = None,
    config_backtest: Optional[BacktestConfig] = None,
) -> ResultadoWalkForward:
    """Roda os ciclos e devolve o conjunto."""
    config = config or ConfigWalkForward()
    resultado = ResultadoWalkForward()

    try:
        pares = janelas_walk_forward(serie, config)
    except DivisaoInvalidaError as e:
        resultado.avisos.append(str(e))
        return resultado

    for i, (treino, teste) in enumerate(pares, start=1):
        medida_treino = Medidas.de_resultado(
            Particao.TRAIN, validador.medir(treino, serie, config_backtest), treino.dias)
        medida_teste = Medidas.de_resultado(
            Particao.VALIDATION, validador.medir(teste, serie, config_backtest), teste.dias)
        resultado.ciclos.append(Ciclo(i, treino, teste, medida_treino, medida_teste))

    if resultado.total < 3:
        resultado.avisos.append(
            f"{resultado.total} ciclo(s) apenas: consistencia com tao poucos ciclos "
            "nao significa muita coisa"
        )
    if resultado.trades_fora < 30:
        resultado.avisos.append(
            f"{resultado.trades_fora} trades fora da amostra somando todos os ciclos: "
            "amostra pequena para concluir"
        )
    return resultado
