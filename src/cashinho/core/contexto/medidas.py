"""As contas do contexto: variacao do dia, volatilidade e como classifica-las.

Todas as funcoes daqui devolvem ``None`` quando nao ha dado suficiente. Isso e'
proposital: a alternativa - devolver zero - viraria "mercado parado" na tela,
que e' uma afirmacao sobre o mercado feita a partir da ausencia de dado.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median, pstdev
from typing import Optional, Sequence

from ...models import Series
from .modelos import NivelDeVolatilidade

MIN_CANDLES_VOLATILIDADE = 20


def variacao_do_dia(serie: Series) -> Optional[float]:
    """Variacao percentual do pregao atual contra o fechamento anterior."""
    if len(serie) < 2:
        return None
    sessoes = serie.sessions()
    if len(sessoes) >= 2 and sessoes[-1] and sessoes[-2]:
        anterior = sessoes[-2][-1].close
        atual = sessoes[-1][-1].close
    else:  # um pregao so: usa a abertura do proprio dia
        atual = serie.candles[-1].close
        anterior = serie.candles[0].open
    if not anterior:
        return None
    return (atual / anterior - 1) * 100


def retornos(valores: Sequence[float]) -> list[float]:
    """Retornos simples entre valores consecutivos."""
    saida = []
    for anterior, atual in zip(valores, valores[1:]):
        if anterior:
            saida.append(atual / anterior - 1)
    return saida


def volatilidade_por_candle(serie: Series, janela: int = 60) -> Optional[float]:
    """Desvio padrao dos retornos, em %, na janela pedida."""
    if len(serie) < MIN_CANDLES_VOLATILIDADE:
        return None
    r = retornos(serie.closes[-janela:])
    if len(r) < MIN_CANDLES_VOLATILIDADE - 1:
        return None
    return pstdev(r) * 100


def volatilidade_historica(serie: Series, janela: int = 60) -> Optional[float]:
    """A mediana das volatilidades das janelas anteriores - a referencia.

    Comparar a volatilidade de agora com um numero fixo nao diz nada: 0,4% ao
    candle e' calmo em um ativo e agitado em outro. A referencia precisa ser o
    proprio historico do instrumento.
    """
    if len(serie) < janela * 2:
        return None
    fechamentos = serie.closes
    amostras = []
    fim = len(fechamentos) - janela  # o trecho recente fica de fora
    passo = max(janela // 2, 1)
    for inicio in range(0, fim, passo):
        r = retornos(fechamentos[inicio:inicio + janela])
        if len(r) >= MIN_CANDLES_VOLATILIDADE - 1:
            amostras.append(pstdev(r) * 100)
    if not amostras:
        return None
    return median(amostras)


def classificar_volatilidade(
    atual: Optional[float], referencia: Optional[float]
) -> NivelDeVolatilidade:
    """Compara a volatilidade de agora com a do proprio historico."""
    if atual is None:
        return NivelDeVolatilidade.INDISPONIVEL
    if not referencia:
        return NivelDeVolatilidade.INDISPONIVEL
    razao = atual / referencia
    if razao >= 2.5:
        return NivelDeVolatilidade.EXTREMA
    if razao >= 1.5:
        return NivelDeVolatilidade.ALTA
    if razao <= 0.6:
        return NivelDeVolatilidade.BAIXA
    return NivelDeVolatilidade.NORMAL


def defasagem_minutos(ts: Optional[datetime], instante: datetime) -> Optional[int]:
    """Quantos minutos o dado esta atras do instante consultado."""
    if ts is None:
        return None
    delta = (instante - ts).total_seconds() / 60
    return max(int(delta), 0)
