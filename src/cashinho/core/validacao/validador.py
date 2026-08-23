"""O validador: roda a estrategia em cada particao e monta o relatorio.

A ordem importa e e' garantida pelo codigo:

1. mede os candidatos em TRAIN;
2. escolhe entre eles em VALIDATION;
3. abre o cofre e mede o escolhido em TEST - **uma vez**.

O passo 3 e' o unico lugar do modulo que toca no TEST, e ele acontece depois
da decisao ja estar tomada. Nada do que sair dali volta para mudar parametro:
se voltar, o numero final deixa de valer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Optional, Sequence

from ...models import Series
from ..backtest.config import BacktestConfig
from ..backtest.engine import BacktestEngine
from ..backtest.models import BacktestResult
from ..strategy.base import Strategy
from .cofre import CofreDeTeste, TesteProtegidoError
from .divisao import DivisaoDeDados, Janela, Particao
from .relatorio import CriteriosDeDegradacao, Medidas, RelatorioDeValidacao
from .selecao import (
    Candidato,
    CriteriosDeSelecao,
    Selecao,
    SelecionadorEmTreino,
)

FabricaDeEstrategia = Callable[[], Strategy]


@dataclass(frozen=True)
class ConfigValidacao:
    """Como cada particao e' medida."""

    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    dias_de_aquecimento: int = 5
    criterios_selecao: CriteriosDeSelecao = field(default_factory=CriteriosDeSelecao)
    criterios_degradacao: CriteriosDeDegradacao = field(default_factory=CriteriosDeDegradacao)


class ValidadorDeEstrategia:
    """Treino, validacao e teste - nesta ordem, e o teste so no fim."""

    def __init__(
        self,
        estrategia: FabricaDeEstrategia,
        config: Optional[ConfigValidacao] = None,
    ):
        self.estrategia = estrategia
        self.config = config or ConfigValidacao()

    # ------------------------------------------------------------------
    def medir(self, janela: Janela, serie_completa: Series,
              config_backtest: Optional[BacktestConfig] = None) -> BacktestResult:
        """Roda o backtest de uma janela, com aquecimento antes dela."""
        base = config_backtest or self.config.backtest
        serie = janela.com_aquecimento(serie_completa, self.config.dias_de_aquecimento)
        rodada = replace(
            base,
            symbol=base.symbol or serie.symbol,
            inicio=janela.inicio,
            fim=janela.fim,
        )
        return BacktestEngine(self.estrategia(), rodada).rodar(serie)

    # ------------------------------------------------------------------
    def validar(
        self,
        divisao: DivisaoDeDados,
        candidatos: Optional[Sequence[Candidato]] = None,
        medir_teste: bool = True,
    ) -> RelatorioDeValidacao:
        """O fluxo completo. ``medir_teste=False`` deixa o cofre fechado."""
        cofre = CofreDeTeste(divisao.teste)
        serie = divisao.serie

        selecao: Optional[Selecao] = None
        config_escolhida = self.config.backtest
        nome = "configuracao unica"

        if candidatos:
            selecionador = SelecionadorEmTreino(
                avaliar=lambda janela, cfg: self.medir(janela, serie, cfg),
                criterios=self.config.criterios_selecao,
            )
            selecao = selecionador.selecionar(divisao, candidatos)
            if not selecao.houve_escolha:
                return RelatorioDeValidacao(
                    divisao, [], cofre, self.config.criterios_degradacao, selecao,
                    candidato="",
                )
            config_escolhida = selecao.escolhido.config
            nome = selecao.escolhido.nome

        medidas = [
            Medidas.de_resultado(
                Particao.TRAIN, self.medir(divisao.treino, serie, config_escolhida),
                divisao.treino.dias),
            Medidas.de_resultado(
                Particao.VALIDATION, self.medir(divisao.validacao, serie, config_escolhida),
                divisao.validacao.dias),
        ]

        if medir_teste:
            # a UNICA abertura do cofre - e depois da escolha ja estar feita
            janela = cofre.abrir(
                f"medicao final de '{nome}', com a configuracao ja escolhida em validacao"
            )
            medidas.append(Medidas.de_resultado(
                Particao.TEST, self.medir(janela, serie, config_escolhida), janela.dias))

        return RelatorioDeValidacao(
            divisao, medidas, cofre, self.config.criterios_degradacao, selecao, nome
        )
