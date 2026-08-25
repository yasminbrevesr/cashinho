from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cashinho.domain.market import CandleSeries
from cashinho.pipeline.indicators import IndicatorPanel


@dataclass(frozen=True, slots=True)
class EntrySignal:
    side: str
    status: str
    score: int
    entry: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    risk_reward: float | None
    reasons: tuple[str, ...]


def evaluate_entry_signal(
    series: CandleSeries,
    panel: IndicatorPanel,
) -> EntrySignal:
    """
    Entry Signal V1.

    Regras simples, deterministicas e explicaveis.
    Usa somente candles fechados e indicadores ja calculados.
    Nao envia ordens.
    """

    candles = series.closed_only()

    if len(candles) < 30:
        return EntrySignal(
            side="NONE",
            status="NÃO OPERAR",
            score=0,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            reasons=("Dados insuficientes.",),
        )

    last = candles.last
    if last is None:
        return EntrySignal(
            side="NONE",
            status="NÃO OPERAR",
            score=0,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            reasons=("Sem candle fechado.",),
        )

    close = last.close
    score_buy = 0
    score_sell = 0
    buy_reasons: list[str] = []
    sell_reasons: list[str] = []

    # ---------------------------------------------------------
    # EMA
    # ---------------------------------------------------------
    ema9 = panel.overlays.get("EMA(9)")
    ema21 = panel.overlays.get("EMA(21)")

    ema9_value = None
    ema21_value = None

    if ema9 is not None:
        values = ema9.last()
        ema9_value = next(iter(values.values()), None)

    if ema21 is not None:
        values = ema21.last()
        ema21_value = next(iter(values.values()), None)

    if ema9_value is not None and ema21_value is not None:
        if ema9_value > ema21_value:
            score_buy += 20
            buy_reasons.append("EMA 9 acima da EMA 21")
        elif ema9_value < ema21_value:
            score_sell += 20
            sell_reasons.append("EMA 9 abaixo da EMA 21")

    # ---------------------------------------------------------
    # VWAP
    # ---------------------------------------------------------
    vwap_result = panel.overlays.get("VWAP")
    if vwap_result is not None:
        values = vwap_result.last()
        vwap_value = next(iter(values.values()), None)

        if vwap_value is not None:
            if close > vwap_value:
                score_buy += 20
                buy_reasons.append("Preço acima da VWAP")
            elif close < vwap_value:
                score_sell += 20
                sell_reasons.append("Preço abaixo da VWAP")

    # ---------------------------------------------------------
    # RSI
    # ---------------------------------------------------------
    rsi_result = panel.oscillators.get("RSI(14)")
    if rsi_result is not None:
        values = rsi_result.last()
        rsi_value = next(iter(values.values()), None)

        if rsi_value is not None:
            if 50 <= rsi_value <= 70:
                score_buy += 15
                buy_reasons.append(f"RSI favorável à compra ({rsi_value:.1f})")

            if 30 <= rsi_value <= 50:
                score_sell += 15
                sell_reasons.append(f"RSI favorável à venda ({rsi_value:.1f})")

    # ---------------------------------------------------------
    # Estrutura simples dos últimos candles
    # ---------------------------------------------------------
    recent = candles.candles[-4:]

    if len(recent) >= 4:
        highs = [c.high for c in recent]
        lows = [c.low for c in recent]

        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            score_buy += 20
            buy_reasons.append("Estrutura recente de máxima e mínima ascendentes")

        if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            score_sell += 20
            sell_reasons.append("Estrutura recente de máxima e mínima descendentes")

    # ---------------------------------------------------------
    # Volume
    # ---------------------------------------------------------
    recent_volume = [c.volume for c in candles.candles[-20:]]

    if recent_volume:
        avg_volume = sum(recent_volume[:-1]) / max(len(recent_volume[:-1]), 1)

        if last.volume > avg_volume:
            score_buy += 10
            score_sell += 10

            buy_reasons.append("Volume acima da média recente")
            sell_reasons.append("Volume acima da média recente")

    # ---------------------------------------------------------
    # Candle de gatilho
    # ---------------------------------------------------------
    if last.close > last.open:
        score_buy += 15
        buy_reasons.append("Último candle fechado comprador")

    elif last.close < last.open:
        score_sell += 15
        sell_reasons.append("Último candle fechado vendedor")

    # ---------------------------------------------------------
    # Decide lado
    # ---------------------------------------------------------
    if score_buy > score_sell:
        side = "BUY"
        score = min(score_buy, 100)
        reasons = tuple(buy_reasons)
    elif score_sell > score_buy:
        side = "SELL"
        score = min(score_sell, 100)
        reasons = tuple(sell_reasons)
    else:
        return EntrySignal(
            side="NONE",
            status="NÃO OPERAR",
            score=0,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            reasons=("Sem vantagem clara entre compra e venda.",),
        )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------
    if score < 60:
        return EntrySignal(
            side=side,
            status="NÃO OPERAR",
            score=score,
            entry=None,
            stop=None,
            target=None,
            risk_reward=None,
            reasons=reasons,
        )

    if score < 75:
        status = "AGUARDANDO GATILHO"
    else:
        status = "ENTRADA LIBERADA"

    # ---------------------------------------------------------
    # Stop e alvo V1
    # ---------------------------------------------------------
    if side == "BUY":
        entry = last.high
        stop = min(c.low for c in candles.candles[-5:])
        risk = entry - stop

        if risk <= 0:
            return EntrySignal(
                side=side,
                status="NÃO OPERAR",
                score=score,
                entry=None,
                stop=None,
                target=None,
                risk_reward=None,
                reasons=reasons + ("Stop inválido.",),
            )

        target = entry + (risk * Decimal("2"))

    else:
        entry = last.low
        stop = max(c.high for c in candles.candles[-5:])
        risk = stop - entry

        if risk <= 0:
            return EntrySignal(
                side=side,
                status="NÃO OPERAR",
                score=score,
                entry=None,
                stop=None,
                target=None,
                risk_reward=None,
                reasons=reasons + ("Stop inválido.",),
            )

        target = entry - (risk * Decimal("2"))

    return EntrySignal(
        side=side,
        status=status,
        score=score,
        entry=entry,
        stop=stop,
        target=target,
        risk_reward=2.0,
        reasons=reasons,
    )