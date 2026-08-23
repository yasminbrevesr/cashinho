"""Selecao de parametros - pequena de proposito.

Este modulo **nao** e' um otimizador. Ele compara um punhado de candidatos
escolhidos a mao, e recusa grades grandes: procurar centenas de combinacoes
em serie curta encontra ruido com facilidade e chama isso de estrategia.

O fluxo e' o classico e o unico permitido aqui:

    TRAIN      -> mede cada candidato
    VALIDATION -> escolhe entre os que passaram
    TEST       -> mede o escolhido UMA vez, no fim

E o TEST nao entra aqui de jeito nenhum: :func:`garantir_sem_teste` barra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from ...models import Series
from ..backtest.models import BacktestResult
from .cofre import TesteProtegidoError, garantir_sem_teste
from .divisao import DivisaoDeDados, Janela, Particao

LIMITE_DE_CANDIDATOS = 12
"""Acima disso o modulo recusa - e' o limite entre comparar e garimpar."""


class GradeGrandeDemaisError(ValueError):
    """Grade de parametros grande o bastante para achar ruido."""


@dataclass(frozen=True)
class Candidato:
    """Uma configuracao a comparar, com nome de gente."""

    nome: str
    config: object  # BacktestConfig, ConfigOportunidade, o que a rodada usar
    descricao: str = ""


@dataclass(frozen=True)
class Medida:
    """O desempenho de um candidato em uma particao."""

    candidato: str
    particao: Particao
    resultado: BacktestResult

    @property
    def retorno_pct(self) -> float:
        return self.resultado.metricas.retorno_total_pct

    @property
    def n_trades(self) -> int:
        return self.resultado.metricas.n_trades

    @property
    def profit_factor(self) -> Optional[float]:
        return self.resultado.metricas.profit_factor

    @property
    def expectancy(self) -> float:
        return self.resultado.metricas.expectancy


@dataclass
class Selecao:
    """O que a selecao decidiu, e com base em que."""

    escolhido: Optional[Candidato]
    motivo: str
    em_treino: list[Medida] = field(default_factory=list)
    em_validacao: list[Medida] = field(default_factory=list)
    descartados: list[tuple[str, str]] = field(default_factory=list)

    @property
    def houve_escolha(self) -> bool:
        return self.escolhido is not None

    def medida(self, candidato: str, particao: Particao) -> Optional[Medida]:
        fonte = self.em_treino if particao is Particao.TRAIN else self.em_validacao
        for m in fonte:
            if m.candidato == candidato:
                return m
        return None

    def para_dict(self) -> dict:
        return {
            "escolhido": self.escolhido.nome if self.escolhido else None,
            "motivo": self.motivo,
            "candidatos": sorted({m.candidato for m in self.em_treino}),
            "descartados": [{"candidato": c, "motivo": m} for c, m in self.descartados],
            "em_treino": [
                {"candidato": m.candidato, "retorno_pct": round(m.retorno_pct, 3),
                 "trades": m.n_trades, "profit_factor": m.profit_factor}
                for m in self.em_treino
            ],
            "em_validacao": [
                {"candidato": m.candidato, "retorno_pct": round(m.retorno_pct, 3),
                 "trades": m.n_trades, "profit_factor": m.profit_factor}
                for m in self.em_validacao
            ],
        }


@dataclass(frozen=True)
class CriteriosDeSelecao:
    """O que um candidato precisa entregar para ser levado a serio."""

    min_trades_treino: int = 10
    min_trades_validacao: int = 5
    profit_factor_minimo: float = 1.0
    exigir_retorno_positivo: bool = True

    def aprova(self, treino: Medida, validacao: Medida) -> tuple[bool, str]:
        if treino.n_trades < self.min_trades_treino:
            return False, f"apenas {treino.n_trades} trades no treino"
        if validacao.n_trades < self.min_trades_validacao:
            return False, f"apenas {validacao.n_trades} trades na validacao"
        if self.exigir_retorno_positivo and validacao.retorno_pct <= 0:
            return False, f"retorno de {validacao.retorno_pct:+.2f}% na validacao"
        pf = validacao.profit_factor
        if pf is not None and pf < self.profit_factor_minimo:
            return False, f"profit factor de {pf:.2f} na validacao"
        return True, ""


class SelecionadorEmTreino:
    """Mede em TRAIN, escolhe em VALIDATION, nunca toca no TEST."""

    def __init__(
        self,
        avaliar: Callable[[Janela, object], BacktestResult],
        criterios: Optional[CriteriosDeSelecao] = None,
    ):
        self.avaliar = avaliar
        self.criterios = criterios or CriteriosDeSelecao()

    def selecionar(self, divisao: DivisaoDeDados,
                   candidatos: Sequence[Candidato]) -> Selecao:
        if not candidatos:
            raise ValueError("informe ao menos um candidato")
        if len(candidatos) > LIMITE_DE_CANDIDATOS:
            raise GradeGrandeDemaisError(
                f"{len(candidatos)} candidatos: o limite aqui e' {LIMITE_DE_CANDIDATOS}. "
                "Este modulo compara alternativas escolhidas a mao; procurar centenas "
                "de combinacoes em serie curta encontra ruido, nao vantagem"
            )
        # a barreira estrutural: se alguem passar TEST, para aqui
        garantir_sem_teste([Particao.TRAIN, Particao.VALIDATION])

        em_treino = [Medida(c.nome, Particao.TRAIN, self.avaliar(divisao.treino, c.config))
                     for c in candidatos]
        em_validacao = [Medida(c.nome, Particao.VALIDATION,
                               self.avaliar(divisao.validacao, c.config))
                        for c in candidatos]

        por_nome = {c.nome: c for c in candidatos}
        aprovados: list[tuple[Candidato, Medida]] = []
        descartados: list[tuple[str, str]] = []
        for treino, validacao in zip(em_treino, em_validacao):
            ok, motivo = self.criterios.aprova(treino, validacao)
            if ok:
                aprovados.append((por_nome[treino.candidato], validacao))
            else:
                descartados.append((treino.candidato, motivo))

        if not aprovados:
            return Selecao(
                escolhido=None,
                motivo="nenhum candidato passou nos criterios minimos na validacao",
                em_treino=em_treino, em_validacao=em_validacao, descartados=descartados,
            )

        # entre os aprovados, o melhor NA VALIDACAO - nao no treino
        escolhido, medida = max(aprovados, key=lambda par: par[1].retorno_pct)
        return Selecao(
            escolhido=escolhido,
            motivo=(f"melhor retorno na validacao entre os {len(aprovados)} aprovados: "
                    f"{medida.retorno_pct:+.2f}% em {medida.n_trades} trades"),
            em_treino=em_treino, em_validacao=em_validacao, descartados=descartados,
        )
