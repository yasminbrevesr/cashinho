"""Contrato comum dos indicadores.

Regras que valem para todos os modulos deste pacote:

1. Entrada padronizada: `CandleSeries`. Nenhum indicador recebe DataFrame
   solto — sem `symbol`, `timeframe` e `source`, o resultado nao seria
   rastreavel ate a origem do dado.
2. Serie fechada obrigatoria (ADR-0003). Calcular sobre o candle em
   formacao produz valor que muda a cada tick e desaparece no fechamento.
3. Nenhum indicador decide nada. Devolvem numeros; interpretacao e
   confluencia pertencem ao Strategy Engine e ao Scoring.
4. Sem Streamlit, sem plotagem, sem I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from cashinho.domain.enums import Timeframe
from cashinho.domain.errors import CashinhoError
from cashinho.domain.market import CandleSeries


class InsufficientDataError(CashinhoError):
    """Amostra menor que o minimo exigido pelo indicador.

    Excecao em vez de coluna inteira de NaN: um retorno vazio seria
    consumido adiante como "sem sinal", que e conclusao diferente de
    "nao foi possivel calcular".
    """


class IndicatorNotApplicableError(CashinhoError):
    """Indicador incompativel com o timeframe ou com o tipo de serie."""


@dataclass(frozen=True, slots=True)
class IndicatorResult:
    """Saida padronizada de qualquer indicador.

    `values` sempre indexado por `open_time` em UTC, alinhado a serie de
    entrada. Indicadores de multiplas linhas (MACD, Bollinger) usam
    varias colunas do mesmo DataFrame em vez de retornos separados, para
    que o alinhamento temporal fique garantido por construcao.
    """

    name: str
    symbol: str
    timeframe: Timeframe
    values: pd.DataFrame
    warmup: int
    params: Mapping[str, float] = field(default_factory=dict)

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(str(c) for c in self.values.columns)

    @property
    def is_empty(self) -> bool:
        return self.values.empty

    def last(self) -> dict[str, float | None]:
        """Ultimo valor de cada linha, ou None quando ainda em aquecimento."""
        if self.values.empty:
            return dict.fromkeys(self.columns)
        row = self.values.iloc[-1]
        return {
            str(column): (None if pd.isna(row[column]) else float(row[column]))
            for column in self.values.columns
        }

    def dropna(self) -> pd.DataFrame:
        """Apenas os periodos ja aquecidos."""
        return self.values.dropna(how="all")


def prepare(
    series: CandleSeries,
    *,
    minimum: int,
    indicator: str,
    intraday_only: bool = False,
) -> pd.DataFrame:
    """Valida a entrada e devolve o DataFrame pronto para calculo.

    Ponto unico de validacao: cada indicador declara seu minimo e recebe
    de volta um frame confiavel, sem repetir as mesmas checagens.
    """
    if intraday_only and not series.timeframe.is_intraday:
        raise IndicatorNotApplicableError(
            f"{indicator} nao se aplica ao timeframe {series.timeframe}: "
            "e um indicador intradiario, ancorado na sessao de negociacao"
        )

    closed = series.require_closed()
    if len(closed) < minimum:
        raise InsufficientDataError(
            f"{indicator} exige ao menos {minimum} candles fechados; "
            f"{closed.symbol} {closed.timeframe} tem {len(closed)}"
        )
    return closed.to_frame()


def validate_period(period: int, *, name: str = "period", minimum: int = 1) -> int:
    """Rejeita periodo invalido na chamada, nao no meio do calculo."""
    if period < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}; recebido {period}")
    return period


def recursive_average(values: pd.Series, period: int, alpha: float) -> pd.Series:
    """Media recursiva com semente na media simples dos `period` primeiros.

    A SEMENTE IMPORTA. `pandas.ewm(adjust=False)` inicia a recursao no
    primeiro valor da serie; as plataformas de grafico iniciam na media
    simples dos `period` primeiros. A recursao seguinte e identica, mas os
    valores iniciais divergem e a diferenca leva dezenas de periodos para
    decair.

    Consequencia pratica: com a semente do pandas, o RSI e o ATR exibidos
    pelo Cashinho nao bateriam com os da corretora em series curtas, e o
    operador teria de escolher em qual acreditar.

    Implementacao: substitui o valor na posicao da semente pela media e
    aplica `ewm` a partir dali, o que mantem o calculo vetorizado e
    exato.
    """
    clean = values.dropna()
    if len(clean) < period:
        return pd.Series(float("nan"), index=values.index, dtype="float64")

    seeded = clean.astype("float64").copy()
    seeded.iloc[period - 1] = float(clean.iloc[:period].mean())
    tail = seeded.iloc[period - 1 :]
    smoothed = tail.ewm(alpha=alpha, adjust=False).mean()
    return smoothed.reindex(values.index)


def exponential_average(values: pd.Series, period: int) -> pd.Series:
    """EMA convencional, fator 2/(period + 1)."""
    return recursive_average(values, period, alpha=2.0 / (period + 1))


def wilder_smoothing(values: pd.Series, period: int) -> pd.Series:
    """Media suavizada de Wilder (RMA), fator 1/period.

    Wilder usa 1/period, e nao o 2/(period+1) da EMA convencional.
    Trocar um pelo outro desloca RSI e ATR o suficiente para mudar
    decisoes, entao a implementacao fica isolada aqui e e usada pelos
    dois indicadores.
    """
    return recursive_average(values, period, alpha=1.0 / period)
