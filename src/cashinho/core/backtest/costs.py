"""Custos de execucao: spread, slippage e taxas.

Backtest sem custo e' propaganda. Aqui o preco que o trade recebe nunca e' o
preco do grafico:

- **spread**: metade do spread e' paga em cada ponta (compra no ask, vende no bid);
- **slippage**: a ordem a mercado sai pior do que o preco visto;
- **taxas**: corretagem (fixa e/ou percentual) e taxas da B3, cobradas nas
  duas pontas.

Ordem limitada no alvo nao leva slippage por padrao - ela ou executa no preco
ou nao executa. Ordem de stop leva, porque vira mercado ao ser disparada.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...models import Direction, arredonda_tick


@dataclass(frozen=True)
class ModeloCustos:
    """Quanto custa entrar e sair de uma operacao.

    Os valores padrao sao uma referencia conservadora para acoes liquidas da
    B3 - confirme corretagem e taxas com a sua corretora antes de tirar
    conclusao de qualquer backtest.
    """

    corretagem_fixa: float = 0.0  # R$ por ordem
    corretagem_pct: float = 0.0  # % sobre o financeiro
    taxas_b3_pct: float = 0.03  # emolumentos + liquidacao, % sobre o financeiro
    spread_ticks: float = 1.0  # spread total do book, em ticks
    slippage_ticks: float = 1.0  # derrapagem de ordem a mercado, em ticks
    slippage_no_alvo: bool = False  # alvo e' ordem limitada: normalmente nao derrapa
    tick: float = 0.01

    def __post_init__(self) -> None:
        for nome in ("corretagem_fixa", "corretagem_pct", "taxas_b3_pct", "spread_ticks", "slippage_ticks"):
            if getattr(self, nome) < 0:
                raise ValueError(f"{nome} nao pode ser negativo")
        if self.tick <= 0:
            raise ValueError("tick precisa ser maior que zero")

    # ------------------------------------------------------------------
    def preco_execucao(
        self,
        preco: float,
        direcao: Direction,
        entrando: bool,
        ordem_limitada: bool = False,
    ) -> float:
        """Preco realmente executado, ja com spread e slippage contra o trade.

        ``direcao`` e' a direcao da POSICAO; ``entrando`` diz se e' a abertura
        (compra em posicao comprada) ou o encerramento (venda).
        """
        comprando = (direcao is Direction.LONG) == entrando
        derrapagem = 0.0 if (ordem_limitada and not self.slippage_no_alvo) else self.slippage_ticks
        ajuste = (self.spread_ticks / 2.0 + derrapagem) * self.tick
        bruto = preco + ajuste if comprando else preco - ajuste
        # arredondamento sempre CONTRA o trade: comprando sobe para o tick,
        # vendendo desce - o contrario devolveria centavos que o book nao da
        modo = "up" if comprando else "down"
        return arredonda_tick(max(bruto, self.tick), self.tick, modo)

    def taxas(self, quantidade: int, preco: float) -> float:
        """Custo de UMA ponta (entrada ou saida)."""
        financeiro = abs(quantidade * preco)
        return (
            self.corretagem_fixa
            + financeiro * self.corretagem_pct / 100.0
            + financeiro * self.taxas_b3_pct / 100.0
        )

    def custo_total(self, quantidade: int, preco_entrada: float, preco_saida: float) -> float:
        """Custo das duas pontas de um trade."""
        return self.taxas(quantidade, preco_entrada) + self.taxas(quantidade, preco_saida)


SEM_CUSTOS = ModeloCustos(taxas_b3_pct=0.0, spread_ticks=0.0, slippage_ticks=0.0)
"""Modelo sem atrito - util para isolar a logica em teste, nunca para decidir."""
