"""Divisao dos dados em TRAIN, VALIDATION e TEST.

Duas regras que a divisao respeita por construcao:

- **cronologica**: treino vem antes da validacao, que vem antes do teste.
  Embaralhar serie temporal e' o atalho mais rapido para um resultado bonito
  e falso;
- **corte no fim do pregao**: as particoes quebram entre dias, nunca no meio
  de um. Cortar as 14h faria a validacao comecar com meio pregao de contexto
  que ela nao viveu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional, Sequence

from ...models import Series


class Particao(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"

    @property
    def rotulo(self) -> str:
        return {"train": "TRAIN", "validation": "VALIDATION", "test": "TEST"}[self.value]

    @property
    def fora_da_amostra(self) -> bool:
        """Particoes que a estrategia nao viu durante o ajuste."""
        return self is not Particao.TRAIN


class DivisaoInvalidaError(ValueError):
    """Divisao impossivel de usar."""


@dataclass(frozen=True)
class Janela:
    """Um pedaco da serie, com o periodo que ele cobre."""

    particao: Particao
    inicio: date
    fim: date
    serie: Series

    @property
    def dias(self) -> int:
        return len({c.ts.date() for c in self.serie.candles})

    @property
    def candles(self) -> int:
        return len(self.serie)

    @property
    def vazia(self) -> bool:
        return self.candles == 0

    def com_aquecimento(self, serie_completa: Series, dias: int = 5) -> Series:
        """A janela mais alguns dias ANTES, so para os indicadores esquentarem.

        Isto nao e' vazamento: usar passado para calcular indicador de um
        periodo posterior e' o sentido normal do tempo. O que nao pode e' o
        contrario - e os trades continuam contando so dentro da janela.
        """
        if dias <= 0:
            return self.serie
        limite = self.inicio - timedelta(days=dias * 2)  # folga para fins de semana
        candles = [c for c in serie_completa.candles
                   if limite <= c.ts.date() <= self.fim]
        return Series(self.serie.symbol, self.serie.timeframe, candles)

    def para_dict(self) -> dict:
        return {
            "particao": self.particao.value,
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "dias": self.dias,
            "candles": self.candles,
        }


def dias_da_serie(serie: Series) -> list[date]:
    return sorted({c.ts.date() for c in serie.candles})


@dataclass(frozen=True)
class DivisaoDeDados:
    """As tres particoes, em ordem cronologica."""

    serie: Series
    treino: Janela
    validacao: Janela
    teste: Janela

    def __post_init__(self) -> None:
        if not (self.treino.fim < self.validacao.inicio <= self.validacao.fim < self.teste.inicio):
            raise DivisaoInvalidaError(
                "as particoes precisam ser cronologicas e sem sobreposicao: "
                f"treino ate {self.treino.fim}, validacao {self.validacao.inicio}"
                f"-{self.validacao.fim}, teste a partir de {self.teste.inicio}"
            )

    @property
    def janelas(self) -> tuple[Janela, Janela, Janela]:
        return (self.treino, self.validacao, self.teste)

    def janela(self, particao: Particao) -> Janela:
        return {Particao.TRAIN: self.treino, Particao.VALIDATION: self.validacao,
                Particao.TEST: self.teste}[particao]

    # ------------------------------------------------------------------
    @classmethod
    def por_percentual(
        cls,
        serie: Series,
        treino: float = 0.6,
        validacao: float = 0.2,
        teste: float = 0.2,
    ) -> "DivisaoDeDados":
        """Divide por proporcao de PREGOES - nao de candles."""
        for nome, valor in (("treino", treino), ("validacao", validacao), ("teste", teste)):
            if valor <= 0:
                raise DivisaoInvalidaError(f"a fatia de {nome} precisa ser maior que zero")
        soma = treino + validacao + teste
        if abs(soma - 1.0) > 1e-6:
            raise DivisaoInvalidaError(f"as fatias precisam somar 1,0 (somam {soma:.3f})")

        dias = dias_da_serie(serie)
        if len(dias) < 3:
            raise DivisaoInvalidaError(
                f"a serie tem {len(dias)} pregao(oes): sao necessarios ao menos 3 "
                "para separar treino, validacao e teste"
            )

        corte1 = max(int(len(dias) * treino), 1)
        corte2 = max(int(len(dias) * (treino + validacao)), corte1 + 1)
        corte2 = min(corte2, len(dias) - 1)
        return cls._montar(serie, dias[:corte1], dias[corte1:corte2], dias[corte2:])

    @classmethod
    def por_data(
        cls,
        serie: Series,
        fim_do_treino: date,
        fim_da_validacao: date,
    ) -> "DivisaoDeDados":
        """Divide por datas: treino ate a primeira, validacao ate a segunda."""
        if fim_do_treino >= fim_da_validacao:
            raise DivisaoInvalidaError(
                "o fim do treino precisa vir antes do fim da validacao"
            )
        dias = dias_da_serie(serie)
        treino = [d for d in dias if d <= fim_do_treino]
        validacao = [d for d in dias if fim_do_treino < d <= fim_da_validacao]
        teste = [d for d in dias if d > fim_da_validacao]

        vazias = [nome for nome, ds in
                  (("treino", treino), ("validacao", validacao), ("teste", teste)) if not ds]
        if vazias:
            raise DivisaoInvalidaError(
                f"particao vazia com estas datas: {', '.join(vazias)}. "
                f"a serie vai de {dias[0]} a {dias[-1]}"
            )
        return cls._montar(serie, treino, validacao, teste)

    @classmethod
    def _montar(cls, serie: Series, treino: Sequence[date], validacao: Sequence[date],
                teste: Sequence[date]) -> "DivisaoDeDados":
        return cls(
            serie=serie,
            treino=_janela(serie, Particao.TRAIN, treino),
            validacao=_janela(serie, Particao.VALIDATION, validacao),
            teste=_janela(serie, Particao.TEST, teste),
        )

    # ------------------------------------------------------------------
    def resumo(self) -> str:
        return " · ".join(
            f"{j.particao.rotulo} {j.dias}d ({j.inicio:%d/%m}-{j.fim:%d/%m})"
            for j in self.janelas
        )

    def para_dict(self) -> dict:
        return {
            "symbol": self.serie.symbol,
            "timeframe": self.serie.timeframe,
            "janelas": [j.para_dict() for j in self.janelas],
        }


def _janela(serie: Series, particao: Particao, dias: Sequence[date]) -> Janela:
    alvo = set(dias)
    candles = [c for c in serie.candles if c.ts.date() in alvo]
    if not candles:
        raise DivisaoInvalidaError(f"particao {particao.rotulo} ficou sem candles")
    return Janela(
        particao=particao, inicio=min(dias), fim=max(dias),
        serie=Series(serie.symbol, serie.timeframe, candles),
    )
