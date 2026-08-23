"""Correlacao entre instrumentos - alinhada pelo timestamp, com amostra junto.

Duas armadilhas que este arquivo evita de proposito:

1. **alinhar por posicao.** Ibovespa e S&P 500 tem pregoes e feriados
   diferentes; casar o i-esimo candle de um com o i-esimo do outro compara
   dias distintos e produz um numero bonito e falso. O alinhamento e' pelo
   timestamp.
2. **correlacao com amostra minuscula.** Com 5 pontos qualquer par parece
   correlacionado. Abaixo de ``MIN_AMOSTRA`` a correlacao nao e' calculada.
"""

from __future__ import annotations

from statistics import pstdev
from typing import Mapping, Optional, Sequence

from ...models import Series
from .medidas import retornos
from .modelos import Correlacao

MIN_AMOSTRA = 30
LIMIAR_RELEVANTE = 0.4


def pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """Correlacao de Pearson. ``None`` quando nao da para calcular."""
    n = min(len(x), len(y))
    if n < 2:
        return None
    x, y = list(x[:n]), list(y[:n])
    mx, my = sum(x) / n, sum(y) / n
    dx, dy = pstdev(x), pstdev(y)
    if dx == 0 or dy == 0:  # serie constante nao tem correlacao definida
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / n
    valor = cov / (dx * dy)
    return max(-1.0, min(1.0, valor))


def retornos_alinhados(a: Series, b: Series) -> tuple[list[float], list[float]]:
    """Retornos das duas series nos timestamps que existem nas duas."""
    por_ts_a = {c.ts: c.close for c in a.candles}
    por_ts_b = {c.ts: c.close for c in b.candles}
    comuns = sorted(set(por_ts_a) & set(por_ts_b))
    if len(comuns) < 2:
        return [], []
    return (retornos([por_ts_a[t] for t in comuns]),
            retornos([por_ts_b[t] for t in comuns]))


def correlacao_entre(nome_a: str, a: Series, nome_b: str, b: Series,
                     janela: str = "", min_amostra: int = MIN_AMOSTRA) -> Optional[Correlacao]:
    ra, rb = retornos_alinhados(a, b)
    if len(ra) < min_amostra:
        return None
    valor = pearson(ra, rb)
    if valor is None:
        return None
    return Correlacao(nome_a, nome_b, valor, len(ra), janela or a.timeframe)


def correlacoes_relevantes(
    series: Mapping[str, Series],
    limiar: float = LIMIAR_RELEVANTE,
    min_amostra: int = MIN_AMOSTRA,
    janela: str = "",
) -> tuple[Correlacao, ...]:
    """Os pares com correlacao acima do limiar, do mais forte para o mais fraco."""
    chaves = sorted(series)
    achadas: list[Correlacao] = []
    for i, a in enumerate(chaves):
        for b in chaves[i + 1:]:
            c = correlacao_entre(a, series[a], b, series[b], janela, min_amostra)
            if c is not None and abs(c.valor) >= limiar:
                achadas.append(c)
    return tuple(sorted(achadas, key=lambda c: -abs(c.valor)))
