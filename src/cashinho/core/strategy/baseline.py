"""Estrategia BASELINE - existe para validar o sistema, nao para operar.

    ATENCAO: esta e' a primeira estrategia do Cashinho e foi escrita para
    exercitar a arquitetura de ponta a ponta (dados -> multi-timeframe ->
    indicadores -> Signal -> tela -> risco). As regras sao propositalmente
    simples e obvias. Ela NAO foi otimizada, NAO foi validada em backtest e
    NAO representa uma estrategia final de day trade.

Regras, todas em cima do candle fechado:

1. **tendencia** - as medias exponenciais 9, 21 e 50 empilhadas na mesma
   ordem (9 > 21 > 50 para alta, invertido para baixa);
2. **inclinacao** - a media de 21 apontando para o lado do vies;
3. **gatilho** - o preco fechando do lado certo da media de 9;
4. **volume** - volume do candle acima da media dos ultimos 20;
5. **ATR** - volatilidade dentro de uma faixa operavel (nem parado, nem
   explodindo).

Estados: ``NONE`` quando nao ha o que acompanhar (dados insuficientes,
volatilidade fora da faixa, medias embaralhadas), ``WAIT`` quando existe
vies mas falta confirmacao, ``BUY``/``SELL`` quando todas as condicoes
obrigatorias estao atendidas e a confianca passa do minimo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...indicators.core import atr as calcula_atr
from ...indicators.core import ema, slope_pct
from ...indicators.volatility import atr_percentual
from ...indicators.volume import volume_relativo
from ...models import Direction, formata_dinheiro
from .base import Strategy, registrar
from .context import StrategyContext
from .models import Action, Factor, Signal

AVISO = (
    "estrategia de validacao da arquitetura - regras simples, sem otimizacao "
    "nem backtest; nao e' uma estrategia final nem recomendacao"
)


@dataclass(frozen=True)
class BaselineConfig:
    """Parametros da baseline. Simples de propósito."""

    ema_curta: int = 9
    ema_media: int = 21
    ema_longa: int = 50
    periodo_volume: int = 20
    atr_periodo: int = 14
    volume_minimo: float = 1.2  # x a media
    atr_min_pct: float = 0.15  # abaixo disso o ativo esta parado
    atr_max_pct: float = 3.0  # acima disso esta explosivo demais
    inclinacao_minima_pct: float = 0.01  # % do preco por candle
    distancia_maxima_atr: float = 2.0  # preco esticado em relacao a media de 21
    confianca_minima: float = 0.6
    stop_atr: float = 1.5
    alvo_atr: float = 3.0

    @property
    def candles_minimos(self) -> int:
        return max(self.ema_longa, self.periodo_volume, self.atr_periodo) + 5


class BaselineTendenciaVolumeATR(Strategy):
    """Tendencia + medias moveis + volume + ATR. Nada alem disso."""

    nome = "baseline-tendencia"
    descricao = "medias 9/21/50 empilhadas, volume acima da media e ATR em faixa operavel"
    timeframe_preferido = "5m"
    experimental = True
    aviso = AVISO

    def __init__(self, config: Optional[BaselineConfig] = None):
        self.config = config or BaselineConfig()

    # ------------------------------------------------------------------
    def avaliar(self, contexto: StrategyContext) -> Signal:
        c = self.config
        if not contexto.tem_candles(c.candles_minimos):
            return self.sinal_vazio(
                contexto,
                f"candles insuficientes: {len(contexto.serie)} de {c.candles_minimos} necessarios",
            )

        serie = contexto.serie
        preco = serie.price
        e_curta = ema(serie.closes, c.ema_curta)[-1]
        e_media = ema(serie.closes, c.ema_media)[-1]
        e_longa = ema(serie.closes, c.ema_longa)[-1]
        atr = calcula_atr(serie.highs, serie.lows, serie.closes, c.atr_periodo)[-1]
        atr_pct = atr_percentual(serie.highs, serie.lows, serie.closes, c.atr_periodo)[-1]
        vrel = volume_relativo(serie.volumes, c.periodo_volume)[-1]
        inclinacao = slope_pct(ema(serie.closes, c.ema_media), 5, preco)

        if None in (e_curta, e_media, e_longa, atr, atr_pct):
            return self.sinal_vazio(contexto, "indicadores ainda sem valor: serie curta demais")

        # --- filtro de volatilidade: vale a pena olhar este ativo agora? ---
        fator_atr = self._fator_atr(atr_pct, atr)
        if not fator_atr.favoravel:
            return self.sinal_vazio(contexto, fator_atr.detalhe, factors=(fator_atr,))

        # --- vies pelo empilhamento das medias ---
        vies = self._vies(e_curta, e_media, e_longa)
        fator_empilhamento = self._fator_empilhamento(vies, e_curta, e_media, e_longa)
        if vies is None:
            return self.sinal_vazio(
                contexto,
                "medias embaralhadas: sem tendencia definida",
                factors=(fator_empilhamento, fator_atr),
            )

        alta = vies is Direction.LONG
        fatores = [
            fator_empilhamento,
            self._fator_inclinacao(alta, inclinacao),
            self._fator_gatilho(alta, preco, e_curta),
            self._fator_volume(vrel),
            fator_atr,
            self._fator_distancia(preco, e_media, atr),
            self._fator_candle(alta, serie),
        ]

        confianca = self._confianca(fatores)
        obrigatorias_ok = all(f.favoravel for f in fatores if f.obrigatorio)
        acionavel = obrigatorias_ok and confianca >= c.confianca_minima
        action = (Action.BUY if alta else Action.SELL) if acionavel else Action.WAIT

        niveis = self._niveis(alta, preco, e_media, atr)
        return Signal(
            symbol=contexto.symbol,
            timestamp=contexto.timestamp,
            timeframe=contexto.timeframe,
            action=action,
            setup=f"{'alta' if alta else 'baixa'}: medias empilhadas + volume + ATR",
            confidence=confianca,
            reasons=self._justificativas(action, fatores, confianca),
            invalidation=self._invalidacao(alta, e_media, niveis),
            strategy=self.nome,
            vies=vies,
            factors=tuple(fatores),
            niveis=niveis,
            experimental=True,
            aviso=AVISO,
        )

    # ------------------------------------------------------------------
    # fatores
    # ------------------------------------------------------------------
    def _vies(self, curta: float, media: float, longa: float) -> Optional[Direction]:
        if curta > media > longa:
            return Direction.LONG
        if curta < media < longa:
            return Direction.SHORT
        return None

    def _fator_empilhamento(self, vies, curta, media, longa) -> Factor:
        c = self.config
        if vies is None:
            detalhe = (
                f"medias fora de ordem (EMA{c.ema_curta} {formata_dinheiro(curta)}, "
                f"EMA{c.ema_media} {formata_dinheiro(media)}, EMA{c.ema_longa} {formata_dinheiro(longa)})"
            )
            return Factor("empilhamento das medias", False, detalhe, peso=1.5, obrigatorio=True)
        sentido = "9 > 21 > 50" if vies is Direction.LONG else "9 < 21 < 50"
        return Factor(
            "empilhamento das medias",
            True,
            f"medias empilhadas para {'alta' if vies is Direction.LONG else 'baixa'} ({sentido})",
            peso=1.5,
            obrigatorio=True,
        )

    def _fator_inclinacao(self, alta: bool, inclinacao: Optional[float]) -> Factor:
        c = self.config
        if inclinacao is None:
            return Factor("inclinacao da media de 21", False, "sem dados para medir a inclinacao",
                          peso=1.0, obrigatorio=True)
        favoravel = inclinacao > c.inclinacao_minima_pct if alta else inclinacao < -c.inclinacao_minima_pct
        sentido = "subindo" if inclinacao > 0 else ("descendo" if inclinacao < 0 else "de lado")
        return Factor(
            "inclinacao da media de 21",
            favoravel,
            f"EMA{c.ema_media} {sentido} ({inclinacao:+.3f}% por candle)",
            peso=1.0,
            obrigatorio=True,
        )

    def _fator_gatilho(self, alta: bool, preco: float, curta: float) -> Factor:
        c = self.config
        favoravel = preco > curta if alta else preco < curta
        lado = "acima" if preco > curta else "abaixo"
        return Factor(
            f"preco x media de {c.ema_curta}",
            favoravel,
            f"fechamento {formata_dinheiro(preco)} {lado} da EMA{c.ema_curta} "
            f"({formata_dinheiro(curta)})",
            peso=1.0,
            obrigatorio=True,
        )

    def _fator_volume(self, vrel: Optional[float]) -> Factor:
        c = self.config
        if vrel is None:
            return Factor("volume", False, "sem media de volume ainda", peso=1.0, obrigatorio=True)
        return Factor(
            "volume",
            vrel >= c.volume_minimo,
            f"volume {vrel:.2f}x a media de {c.periodo_volume} candles "
            f"(minimo {c.volume_minimo:.2f}x)",
            peso=1.0,
            obrigatorio=True,
        )

    def _fator_atr(self, atr_pct: float, atr: float) -> Factor:
        c = self.config
        dentro = c.atr_min_pct <= atr_pct <= c.atr_max_pct
        if dentro:
            detalhe = f"ATR {formata_dinheiro(atr)} ({atr_pct:.2f}% do preco), dentro da faixa operavel"
        elif atr_pct < c.atr_min_pct:
            detalhe = f"ativo parado: ATR de {atr_pct:.2f}% abaixo do minimo de {c.atr_min_pct:.2f}%"
        else:
            detalhe = f"volatilidade excessiva: ATR de {atr_pct:.2f}% acima do maximo de {c.atr_max_pct:.2f}%"
        return Factor("volatilidade (ATR)", dentro, detalhe, peso=0.5, obrigatorio=True)

    def _fator_distancia(self, preco: float, media: float, atr: float) -> Factor:
        c = self.config
        distancia = abs(preco - media) / atr if atr else 0.0
        perto = distancia <= c.distancia_maxima_atr
        return Factor(
            f"distancia da media de {c.ema_media}",
            perto,
            f"preco a {distancia:.1f} ATR da EMA{c.ema_media} "
            f"(esticado acima de {c.distancia_maxima_atr:.1f})",
            peso=0.5,
        )

    def _fator_candle(self, alta: bool, serie) -> Factor:
        ultimo = serie.last
        a_favor = ultimo.bullish if alta else ultimo.bearish
        if ultimo.close == ultimo.open:
            return Factor("candle de confirmacao", None, "candle sem corpo (doji)", peso=0.5)
        return Factor(
            "candle de confirmacao",
            a_favor,
            f"ultimo candle {'de alta' if ultimo.bullish else 'de baixa'}, "
            f"{'a favor' if a_favor else 'contra'} o vies",
            peso=0.5,
        )

    # ------------------------------------------------------------------
    def _confianca(self, fatores: list[Factor]) -> float:
        total = sum(f.peso for f in fatores)
        if total <= 0:
            return 0.0
        favor = sum(f.peso for f in fatores if f.favoravel is True)
        return round(favor / total, 3)

    def _niveis(self, alta: bool, preco: float, media: float, atr: float) -> dict:
        """Precos de REFERENCIA. Nao sao ordens: quem dimensiona e' o risco."""
        c = self.config
        if alta:
            stop = min(media, preco - c.stop_atr * atr)
            alvo = preco + c.alvo_atr * atr
        else:
            stop = max(media, preco + c.stop_atr * atr)
            alvo = preco - c.alvo_atr * atr
        return {
            "entrada_referencia": preco,
            "stop_referencia": stop,
            "alvo_referencia": alvo,
            "atr": atr,
        }

    def _justificativas(self, action: Action, fatores: list[Factor], confianca: float) -> tuple[str, ...]:
        favoraveis = [f for f in fatores if f.favoravel is True]
        faltando = [f for f in fatores if f.favoravel is False and f.obrigatorio]
        razoes = [f.detalhe for f in favoraveis]
        if action is Action.WAIT:
            if faltando:
                razoes.append(
                    "falta para acionar: " + "; ".join(f.nome for f in faltando)
                )
            else:
                razoes.append(
                    f"confianca de {confianca:.0%} abaixo do minimo de "
                    f"{self.config.confianca_minima:.0%}"
                )
        return tuple(razoes)

    def _invalidacao(self, alta: bool, media: float, niveis: dict) -> str:
        c = self.config
        lado = "abaixo" if alta else "acima"
        stop = niveis["stop_referencia"]
        # quando o stop de referencia cai em cima da propria media, nao vale
        # repetir o mesmo numero duas vezes na frase
        extra = (
            ""
            if abs(stop - media) < 0.005
            else f" ou perda do nivel de referencia {formata_dinheiro(stop)}"
        )
        return (
            f"fechamento {lado} da EMA{c.ema_media} ({formata_dinheiro(media)}){extra}; "
            f"o vies tambem cai se as medias desempilharem"
        )


registrar(BaselineTendenciaVolumeATR.nome, BaselineTendenciaVolumeATR)
