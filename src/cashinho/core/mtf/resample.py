"""Reamostragem de candles ancorada na sessao da B3."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

from ...models import BRT, Candle, Series
from .errors import ConfiguracaoInvalidaError
from .session import SESSAO_B3, Sessao
from .timeframes import Bar, Timeframe, agrega, parse_timeframe


def janela(ts: datetime, tf: Timeframe, sessao: Sessao = SESSAO_B3) -> Optional[tuple[datetime, datetime]]:
    """Janela ``(inicio, fim)`` do candle de ``tf`` que contem o instante ``ts``.

    A contagem comeca na abertura do pregao e o ultimo balde do dia e'
    truncado no fechamento - assim nenhum candle "fecha" fora da sessao.
    """
    limites = sessao.sessao_de(ts)
    if limites is None:
        return None
    abre, fecha = limites
    if tf.sessao_inteira:
        return abre, fecha
    dur = timedelta(minutes=tf.minutos)
    decorrido = (ts.astimezone(BRT) - abre) // dur
    inicio = abre + decorrido * dur
    fim = min(inicio + dur, fecha)
    return inicio, fim


def janela_do_candle(
    candle: Candle,
    tf: Timeframe,
    sessao: Sessao = SESSAO_B3,
    rotulagem: str = "abertura",
) -> Optional[tuple[datetime, datetime]]:
    """Janela de um candle ja pronto, respeitando a convencao de rotulagem.

    Feeds diferentes carimbam a barra na abertura (padrao do yfinance e do
    MetaTrader) ou no fechamento (algumas corretoras). ``rotulagem`` diz qual
    convencao usar para descobrir a que janela o candle pertence.
    """
    ts = candle.ts.astimezone(BRT)
    if rotulagem == "fechamento":
        # o carimbo e' o fim da barra: recuamos um instante para cair dentro dela
        ts = ts - timedelta(microseconds=1)
    elif rotulagem != "abertura":
        raise ConfiguracaoInvalidaError(
            f"rotulagem invalida: {rotulagem!r} (use 'abertura' ou 'fechamento')"
        )
    return janela(ts, tf, sessao)


def reamostrar(
    serie: Series,
    destino: str | Timeframe,
    base: str | Timeframe | None = None,
    sessao: Sessao = SESSAO_B3,
    rotulagem: str = "abertura",
    descartar_fora_da_sessao: bool = True,
) -> list[Bar]:
    """Agrega uma serie base em barras do timeframe ``destino``.

    Devolve :class:`Bar`, com a janela de cada barra, para que o motor saiba
    quando cada uma passa a ser consultavel. Barras sao marcadas como
    ``dados_parciais`` quando os candles base nao cobrem a janela inteira
    (buraco no feed ou barra ainda em formacao).
    """
    tf = parse_timeframe(destino)
    tf_base = parse_timeframe(base) if base is not None else parse_timeframe(serie.timeframe)
    if not tf.eh_multiplo_de(tf_base):
        raise ConfiguracaoInvalidaError(
            f"{tf.rotulo} nao e' multiplo de {tf_base.rotulo}: nao da para reamostrar sem inventar dados"
        )

    minutos_base = tf_base.duracao_minutos(sessao.duracao_minutos())
    grupos: dict[tuple[datetime, datetime], list[Candle]] = {}
    ordem: list[tuple[datetime, datetime]] = []

    for c in sorted(serie.candles, key=lambda x: x.ts):
        j = janela_do_candle(c, tf, sessao, rotulagem)
        if j is None:
            if descartar_fora_da_sessao:
                continue
            inicio = c.ts.astimezone(BRT)
            j = (inicio, inicio + timedelta(minutes=minutos_base))
        if j not in grupos:
            grupos[j] = []
            ordem.append(j)
        grupos[j].append(c)

    bars: list[Bar] = []
    for inicio, fim in ordem:
        candles = grupos[(inicio, fim)]
        agregado = agrega(candles, inicio)
        if agregado is None:  # pragma: no cover - grupo nunca fica vazio
            continue
        cobertura = len(candles) * minutos_base
        esperado = int((fim - inicio).total_seconds() // 60)
        bars.append(
            Bar(
                timeframe=tf.rotulo,
                inicio=inicio,
                fim=fim,
                candle=agregado,
                n_base=len(candles),
                dados_parciais=cobertura < esperado,
            )
        )
    return bars


def para_bars(
    serie: Series,
    tf: str | Timeframe,
    sessao: Sessao = SESSAO_B3,
    rotulagem: str = "abertura",
) -> list[Bar]:
    """Envelopa candles ja no timeframe alvo em :class:`Bar`, sem reagregar.

    Usado quando a serie vem pronta do provedor (ou e' injetada num teste):
    cada candle recebe a janela da sessao a que pertence, inclusive quando
    ainda esta em formacao.
    """
    timeframe = parse_timeframe(tf)
    bars: list[Bar] = []
    for c in sorted(serie.candles, key=lambda x: x.ts):
        j = janela_do_candle(c, timeframe, sessao, rotulagem)
        if j is None:
            continue
        inicio, fim = j
        candle = c if c.ts.astimezone(BRT) == inicio else Candle(inicio, c.open, c.high, c.low, c.close, c.volume)
        bars.append(Bar(timeframe.rotulo, inicio, fim, candle))
    return bars
