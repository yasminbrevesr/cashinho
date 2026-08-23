"""Como uma estrategia usa o contexto - e o que ela nao consegue fazer com ele.

O enunciado desta camada e' curto: *o contexto pode pesar, mas nao pode gerar
operacao sozinho*. Aqui isso nao e' recomendacao, e' o formato da funcao:

- ``aplicar_contexto`` recebe um ``Signal`` **que ja existe** e devolve outro
  com a mesma ``action``. Nao ha caminho de codigo que troque WAIT por BUY;
- um sinal que nao e' acionavel nao ganha confianca nenhuma do contexto. Um
  WAIT com confianca inflada seria uma operacao entrando pela porta dos
  fundos, mais adiante no pipeline;
- o ajuste e' limitado a ``LIMITE_DE_AJUSTE``. Contexto bom nao transforma
  leitura fraca em leitura forte.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from ...models import Direction
from ..strategy.base import Strategy
from ..strategy.context import StrategyContext
from ..strategy.models import Action, Factor, Signal
from .modelos import MarketContext, NivelDeVolatilidade, RegimeDeMercado

LIMITE_DE_AJUSTE = 0.08
NOME_DO_FATOR = "contexto de mercado"


def fator_de_contexto(
    contexto: Optional[MarketContext],
    vies: Optional[Direction],
    limite: float = LIMITE_DE_AJUSTE,
) -> tuple[Factor, float]:
    """Devolve o fator a exibir e o ajuste de confianca (-limite..+limite)."""
    if contexto is None:
        return Factor(NOME_DO_FATOR, None, "sem contexto de mercado carregado"), 0.0

    if not contexto.data_quality.confiavel:
        return Factor(
            NOME_DO_FATOR, None,
            f"qualidade dos dados {contexto.data_quality.nivel.rotulo}: "
            "contexto lido, mas nao usado para pesar",
        ), 0.0

    if contexto.market_regime is RegimeDeMercado.ESTRESSE:
        return Factor(
            NOME_DO_FATOR, False,
            f"mercado em estresse (volatilidade {contexto.volatility.rotulo.lower()}): "
            "ambiente contra qualquer leitura",
        ), -limite

    if vies is None or not contexto.market_regime.conhecido:
        return Factor(
            NOME_DO_FATOR, None,
            f"regime {contexto.market_regime.rotulo}: nao pesa a favor nem contra",
        ), 0.0

    a_favor = (
        (vies is Direction.LONG and contexto.favorece_compra)
        or (vies is Direction.SHORT and contexto.favorece_venda)
    )
    contra = (
        (vies is Direction.LONG and contexto.favorece_venda)
        or (vies is Direction.SHORT and contexto.favorece_compra)
    )

    if a_favor:
        return Factor(
            NOME_DO_FATOR, True,
            f"regime {contexto.market_regime.rotulo} acompanha a leitura "
            f"(Ibovespa em {contexto.ibovespa_direction.rotulo.lower()})",
        ), limite
    if contra:
        return Factor(
            NOME_DO_FATOR, False,
            f"regime {contexto.market_regime.rotulo} contraria a leitura "
            f"(Ibovespa em {contexto.ibovespa_direction.rotulo.lower()})",
        ), -limite
    return Factor(
        NOME_DO_FATOR, None,
        f"regime {contexto.market_regime.rotulo}: ambiente sem direcao definida",
    ), 0.0


def aplicar_contexto(
    sinal: Signal,
    contexto: Optional[MarketContext],
    limite: float = LIMITE_DE_AJUSTE,
) -> Signal:
    """Anexa o contexto a um sinal existente. **Nunca muda a ``action``.**"""
    fator, ajuste = fator_de_contexto(contexto, sinal.vies, limite)

    # sinal que nao pede decisao agora nao recebe confianca do contexto:
    # inflar um WAIT seria deixar o contexto empurrar uma operacao adiante
    if not sinal.action.acionavel:
        ajuste = 0.0

    confianca = max(0.0, min(1.0, sinal.confidence + ajuste))
    extras = dict(sinal.extras)
    extras["contexto"] = contexto

    razoes = sinal.reasons
    if ajuste and fator.favoravel is not None:
        razoes = razoes + (fator.detalhe,)

    novo = replace(
        sinal,
        confidence=confianca,
        factors=sinal.factors + (fator,),
        reasons=razoes,
        extras=extras,
    )
    # invariante da camada, verificada aqui e nos testes: o contexto nao cria
    # nem apaga uma operacao - ele so descreve o ambiente em volta dela
    assert novo.action is sinal.action
    return novo


class EstrategiaComContexto(Strategy):
    """Embrulha qualquer estrategia e anexa o contexto ao sinal dela.

    A estrategia embrulhada nao precisa saber que o contexto existe - e nao
    ganha poder nenhum por causa dele.
    """

    def __init__(
        self,
        estrategia: Strategy,
        contexto: Optional[MarketContext] = None,
        carregar: Optional[Callable[[StrategyContext], Optional[MarketContext]]] = None,
        limite: float = LIMITE_DE_AJUSTE,
    ):
        self.estrategia = estrategia
        self.contexto = contexto
        self.carregar = carregar
        self.limite = limite
        self.nome = f"{estrategia.nome} + contexto"
        self.descricao = estrategia.descricao
        self.timeframe_preferido = estrategia.timeframe_preferido
        self.experimental = estrategia.experimental
        self.aviso = estrategia.aviso

    def avaliar(self, contexto: StrategyContext) -> Signal:
        sinal = self.estrategia.avaliar(contexto)
        mercado = self.contexto
        if self.carregar is not None:
            mercado = self.carregar(contexto)
        return aplicar_contexto(sinal, mercado, self.limite)
