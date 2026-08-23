"""Como cada camada e' lida - de candles fechados para um estado nomeado.

Cada leitor recebe a serie JA fechada do seu timeframe e o instante em que o
ultimo candle dela fechou. Nenhum leitor conhece as outras camadas: quem
cruza as leituras sao as regras. Assim uma camada nao pode "espiar" outra e
nao ha caminho para informacao de um timeframe vazar para o outro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...indicators.core import atr as calcula_atr
from ...indicators.core import ema, slope_pct
from ...indicators.volume import volume_relativo
from ...models import Direction, Series, formata_dinheiro
from ..structure import EstruturaConfig, analisar_estrutura
from ..structure.models import Regime, TipoEvento
from .estados import ContextState, SetupState, TrendState, TriggerState, Vies
from .modelos import Context, Setup, Trend, Trigger


@dataclass(frozen=True)
class ConfigLeitura:
    """Parametros dos leitores. Nenhum numero magico solto no codigo."""

    ema_curta: int = 9
    ema_media: int = 21
    ema_longa: int = 50
    atr_periodo: int = 14
    inclinacao_minima_pct: float = 0.01
    volume_gatilho: float = 1.3
    periodo_volume: int = 20
    estrutura: EstruturaConfig = EstruturaConfig()
    stop_atr: float = 1.5
    alvo_em_r: float = 2.0

    @property
    def minimo_candles(self) -> int:
        return self.ema_longa + 5


@dataclass(frozen=True)
class _Vies:
    vies: Vies
    forca: float
    razoes: tuple[str, ...]


def _classifica_vies(serie: Series, cfg: ConfigLeitura) -> _Vies:
    """Empilhamento das medias + inclinacao: a leitura direcional de base."""
    if len(serie) < cfg.minimo_candles:
        return _Vies(Vies.NEUTRAL, 0.0, (f"apenas {len(serie)} candles fechados",))

    closes = serie.closes
    curta = ema(closes, cfg.ema_curta)[-1]
    media = ema(closes, cfg.ema_media)[-1]
    longa = ema(closes, cfg.ema_longa)[-1]
    if None in (curta, media, longa):
        return _Vies(Vies.NEUTRAL, 0.0, ("medias ainda sem valor",))

    preco = serie.price
    inclinacao = slope_pct(ema(closes, cfg.ema_media), 5, preco) or 0.0
    alta = curta > media > longa
    baixa = curta < media < longa

    if alta:
        criterios = [
            (True, f"medias empilhadas para alta ({cfg.ema_curta} > {cfg.ema_media} > {cfg.ema_longa})"),
            (preco > media, f"preco {formata_dinheiro(preco)} acima da EMA{cfg.ema_media}"),
            (inclinacao > cfg.inclinacao_minima_pct, f"EMA{cfg.ema_media} subindo ({inclinacao:+.3f}%/candle)"),
        ]
        vies = Vies.BULLISH
    elif baixa:
        criterios = [
            (True, f"medias empilhadas para baixa ({cfg.ema_curta} < {cfg.ema_media} < {cfg.ema_longa})"),
            (preco < media, f"preco {formata_dinheiro(preco)} abaixo da EMA{cfg.ema_media}"),
            (inclinacao < -cfg.inclinacao_minima_pct, f"EMA{cfg.ema_media} descendo ({inclinacao:+.3f}%/candle)"),
        ]
        vies = Vies.BEARISH
    else:
        return _Vies(
            Vies.NEUTRAL, 0.0,
            (f"medias fora de ordem (EMA{cfg.ema_curta} {formata_dinheiro(curta)}, "
             f"EMA{cfg.ema_media} {formata_dinheiro(media)}, EMA{cfg.ema_longa} {formata_dinheiro(longa)})",),
        )

    atendidos = [texto for ok, texto in criterios if ok]
    return _Vies(vies, round(len(atendidos) / len(criterios), 3), tuple(atendidos))


# ---------------------------------------------------------------------------
# camadas
# ---------------------------------------------------------------------------


def ler_context(serie: Series, fechado_em: datetime, lido_em: datetime,
                cfg: ConfigLeitura = ConfigLeitura()) -> Context:
    """Contexto: o pano de fundo, lido no timeframe mais alto."""
    leitura = _classifica_vies(serie, cfg)
    estado = {
        Vies.BULLISH: ContextState.BULLISH,
        Vies.BEARISH: ContextState.BEARISH,
        Vies.NEUTRAL: ContextState.NEUTRAL,
    }[leitura.vies]
    return Context(
        papel="context", timeframe=serie.timeframe, estado=estado,
        ts=serie.last.ts, fechado_em=fechado_em, lido_em=lido_em,
        forca=leitura.forca, razoes=leitura.razoes,
        detalhes={"preco": serie.price, "candles": len(serie)},
    )


def ler_trend(serie: Series, fechado_em: datetime, lido_em: datetime,
              cfg: ConfigLeitura = ConfigLeitura()) -> Trend:
    """Tendencia: a direcao dominante no timeframe intermediario."""
    leitura = _classifica_vies(serie, cfg)
    estado = {
        Vies.BULLISH: TrendState.BULLISH,
        Vies.BEARISH: TrendState.BEARISH,
        Vies.NEUTRAL: TrendState.SIDEWAYS,
    }[leitura.vies]
    return Trend(
        papel="trend", timeframe=serie.timeframe, estado=estado,
        ts=serie.last.ts, fechado_em=fechado_em, lido_em=lido_em,
        forca=leitura.forca, razoes=leitura.razoes,
        detalhes={"preco": serie.price, "candles": len(serie)},
    )


def ler_setup(serie: Series, fechado_em: datetime, lido_em: datetime,
              cfg: ConfigLeitura = ConfigLeitura()) -> Setup:
    """Setup: que formacao o timeframe de operacao esta desenhando.

    Reaproveita o modulo de estrutura - pullback, rompimento e falso
    rompimento ja sao eventos objetivos de la.
    """
    if len(serie) < cfg.estrutura.pivo_esquerda + cfg.estrutura.pivo_direita + 3:
        return Setup(
            papel="setup", timeframe=serie.timeframe, estado=SetupState.NONE,
            ts=serie.last.ts, fechado_em=fechado_em, lido_em=lido_em,
            razoes=(f"apenas {len(serie)} candles fechados",),
            detalhes={"vies": Vies.NEUTRAL.value},
        )

    estrutura = analisar_estrutura(serie, cfg.estrutura)
    estado = SetupState.NONE
    vies = Vies.NEUTRAL
    razoes: list[str] = []
    forca = 0.0

    pullback = estrutura.pullback
    rompimento = estrutura.rompimento
    falso = estrutura.falso_rompimento

    if pullback is not None:
        estado = SetupState.PULLBACK
        vies = Vies.de_direcao(pullback.direcao)
        forca = pullback.forca
        razoes.append(pullback.descricao)
    elif falso is not None:
        estado = SetupState.FAILED_BREAKOUT
        vies = Vies.de_direcao(falso.direcao)
        forca = falso.forca
        razoes.append(falso.descricao)
    elif rompimento is not None:
        estado = SetupState.BREAKOUT
        vies = Vies.de_direcao(rompimento.direcao)
        forca = rompimento.forca
        razoes.append(rompimento.descricao)
    elif estrutura.tendencia.regime is Regime.LATERAL and (estrutura.suporte or estrutura.resistencia):
        proximo = _borda_do_range(estrutura, cfg)
        if proximo is not None:
            estado, vies, forca, texto = proximo
            razoes.append(texto)

    if not razoes:
        razoes.append(f"sem formacao relevante ({estrutura.tendencia.regime.value})")

    atr = estrutura.atr
    return Setup(
        papel="setup", timeframe=serie.timeframe, estado=estado,
        ts=serie.last.ts, fechado_em=fechado_em, lido_em=lido_em,
        forca=forca, razoes=tuple(razoes),
        detalhes={
            "vies": vies.value,
            "preco": estrutura.preco,
            "atr": atr,
            "regime": estrutura.tendencia.regime.value,
            "suporte": estrutura.suporte.mid if estrutura.suporte else None,
            "resistencia": estrutura.resistencia.mid if estrutura.resistencia else None,
            "zona_fib": (estrutura.fib.zona_do_preco(estrutura.preco).nome
                         if estrutura.fib and estrutura.fib.zona_do_preco(estrutura.preco) else None),
        },
    )


def _borda_do_range(estrutura, cfg: ConfigLeitura):
    """Preco encostado na borda de um range lateral."""
    tolerancia = estrutura.atr * 0.5
    preco = estrutura.preco
    if estrutura.suporte and estrutura.suporte.distancia(preco) <= tolerancia:
        return (SetupState.RANGE_EDGE, Vies.BULLISH, estrutura.suporte.forca,
                f"preco na borda inferior do range, sobre o suporte "
                f"{formata_dinheiro(estrutura.suporte.mid)}")
    if estrutura.resistencia and estrutura.resistencia.distancia(preco) <= tolerancia:
        return (SetupState.RANGE_EDGE, Vies.BEARISH, estrutura.resistencia.forca,
                f"preco na borda superior do range, sob a resistencia "
                f"{formata_dinheiro(estrutura.resistencia.mid)}")
    return None


def ler_trigger(serie: Series, fechado_em: datetime, lido_em: datetime,
                cfg: ConfigLeitura = ConfigLeitura()) -> Trigger:
    """Gatilho: o que o ultimo candle fechado fez, mecanicamente."""
    if len(serie) < max(cfg.ema_curta + 2, 3):
        return Trigger(
            papel="trigger", timeframe=serie.timeframe, estado=TriggerState.NONE,
            ts=serie.last.ts, fechado_em=fechado_em, lido_em=lido_em,
            razoes=(f"apenas {len(serie)} candles fechados",),
            detalhes={"vies": Vies.NEUTRAL.value},
        )

    ultimo = serie.candles[-1]
    anterior = serie.candles[-2]
    vrel = volume_relativo(serie.volumes, cfg.periodo_volume)[-1] or 1.0
    medias = ema(serie.closes, cfg.ema_curta)
    curta = medias[-1]
    curta_anterior = medias[-2] if len(medias) > 1 else None

    estado = TriggerState.NONE
    vies = Vies.NEUTRAL
    razoes: list[str] = []
    forca = 0.0

    rompeu_alta = ultimo.close > anterior.high
    rompeu_baixa = ultimo.close < anterior.low
    volume_ok = vrel >= cfg.volume_gatilho

    if (rompeu_alta or rompeu_baixa) and volume_ok:
        estado = TriggerState.BREAKOUT_WITH_VOLUME
        vies = Vies.BULLISH if rompeu_alta else Vies.BEARISH
        forca = min(1.0, 0.5 + vrel / 4.0)
        razoes.append(
            f"fechou {'acima da maxima' if rompeu_alta else 'abaixo da minima'} do candle "
            f"anterior com {vrel:.2f}x o volume medio"
        )
    elif curta is not None and curta_anterior is not None:
        retomou_alta = anterior.close <= curta_anterior and ultimo.close > curta
        retomou_baixa = anterior.close >= curta_anterior and ultimo.close < curta
        if retomou_alta or retomou_baixa:
            estado = TriggerState.MA_RECLAIM
            vies = Vies.BULLISH if retomou_alta else Vies.BEARISH
            forca = 0.5 + (0.2 if volume_ok else 0.0)
            razoes.append(
                f"fechamento retomou a EMA{cfg.ema_curta} "
                f"({formata_dinheiro(curta)}) {'por cima' if retomou_alta else 'por baixo'}"
            )

    if estado is TriggerState.NONE:
        corpo = max(ultimo.body, ultimo.range * 0.05, 1e-9)
        if ultimo.lower_shadow >= 2 * corpo and ultimo.close > ultimo.open:
            estado, vies, forca = TriggerState.REJECTION_WICK, Vies.BULLISH, 0.45
            razoes.append("candle de rejeicao com sombra inferior longa")
        elif ultimo.upper_shadow >= 2 * corpo and ultimo.close < ultimo.open:
            estado, vies, forca = TriggerState.REJECTION_WICK, Vies.BEARISH, 0.45
            razoes.append("candle de rejeicao com sombra superior longa")

    if not razoes:
        razoes.append(f"nenhum gatilho no candle de {ultimo.ts:%H:%M} (volume {vrel:.2f}x)")

    return Trigger(
        papel="trigger", timeframe=serie.timeframe, estado=estado,
        ts=ultimo.ts, fechado_em=fechado_em, lido_em=lido_em,
        forca=round(forca, 3), razoes=tuple(razoes),
        detalhes={"vies": vies.value, "preco": ultimo.close, "volume_relativo": round(vrel, 2)},
    )


LEITORES = {
    "context": ler_context,
    "trend": ler_trend,
    "setup": ler_setup,
    "trigger": ler_trigger,
}
