"""Metricas de desempenho, calculadas a partir dos trades e da curva de capital.

Duas escolhas que mudam os numeros e por isso ficam explicitas:

- **tudo liquido de custos** - resultado de trade aqui ja desconta corretagem,
  taxas, spread e slippage;
- **Sharpe e Sortino sobre retornos diarios**, anualizados por raiz de 252.
  Com poucos dias de dados esses numeros dizem pouco: abaixo de dois dias eles
  saem como ``None`` em vez de um numero bonito e sem sentido.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from .models import BacktestTrade, Metricas, PontoEquity

DIAS_DE_PREGAO_NO_ANO = 252


def calcular(
    trades: Sequence[BacktestTrade],
    equity: Sequence[PontoEquity],
    capital_inicial: float,
) -> Metricas:
    """Todas as metricas de uma rodada."""
    m = Metricas()
    capital_final = equity[-1].equity if equity else capital_inicial
    m.retorno_total = capital_final - capital_inicial
    m.retorno_total_pct = (m.retorno_total / capital_inicial * 100.0) if capital_inicial else 0.0

    resultados = [t.resultado for t in trades]
    ganhos = [r for r in resultados if r > 0]
    perdas = [-r for r in resultados if r < 0]

    m.n_trades = len(trades)
    m.vencedores = len(ganhos)
    m.perdedores = len(perdas)
    m.empates = m.n_trades - m.vencedores - m.perdedores
    m.custos_totais = sum(t.custos for t in trades)

    if m.n_trades:
        m.win_rate = m.vencedores / m.n_trades
        m.loss_rate = m.perdedores / m.n_trades
        m.melhor_trade = max(resultados)
        m.pior_trade = min(resultados)
        m.expectancy_em_r = sum(t.resultado_em_r for t in trades) / m.n_trades

    m.ganho_medio = sum(ganhos) / len(ganhos) if ganhos else 0.0
    m.perda_media = sum(perdas) / len(perdas) if perdas else 0.0
    m.payoff = (m.ganho_medio / m.perda_media) if m.perda_media else None
    m.expectancy = m.win_rate * m.ganho_medio - m.loss_rate * m.perda_media
    m.profit_factor = (sum(ganhos) / sum(perdas)) if perdas else None

    m.maior_sequencia_ganhos = _maior_sequencia(resultados, positiva=True)
    m.maior_sequencia_perdas = _maior_sequencia(resultados, positiva=False)

    m.max_drawdown, m.max_drawdown_pct = max_drawdown(equity, capital_inicial)

    diarios = retornos_diarios(equity, capital_inicial)
    m.dias = len(diarios)
    m.sharpe = sharpe(diarios)
    m.sortino = sortino(diarios)

    m.exposicao_tempo_pct, m.exposicao_media_pct = exposicao(equity)
    return m


# ---------------------------------------------------------------------------


def _maior_sequencia(resultados: Sequence[float], positiva: bool) -> int:
    maior = atual = 0
    for r in resultados:
        conta = r > 0 if positiva else r < 0
        atual = atual + 1 if conta else 0
        maior = max(maior, atual)
    return maior


def max_drawdown(equity: Sequence[PontoEquity], capital_inicial: float) -> tuple[float, float]:
    """Maior queda entre um pico da curva e o vale seguinte (R$ e %)."""
    if not equity:
        return 0.0, 0.0
    pico = capital_inicial
    pior_valor = 0.0
    pior_pct = 0.0
    for p in equity:
        pico = max(pico, p.equity)
        queda = pico - p.equity
        if queda > pior_valor:
            pior_valor = queda
        pct = (queda / pico * 100.0) if pico else 0.0
        if pct > pior_pct:
            pior_pct = pct
    return pior_valor, pior_pct


def retornos_diarios(equity: Sequence[PontoEquity], capital_inicial: float) -> list[float]:
    """Retorno percentual de cada dia, do fechamento anterior ao do dia."""
    if not equity:
        return []
    por_dia: dict = {}
    for p in equity:
        por_dia[p.dia] = p.equity  # fica o ultimo do dia
    anterior = capital_inicial
    saida: list[float] = []
    for dia in sorted(por_dia):
        atual = por_dia[dia]
        if anterior:
            saida.append(atual / anterior - 1.0)
        anterior = atual
    return saida


def _media(v: Sequence[float]) -> float:
    return sum(v) / len(v) if v else 0.0


def _desvio_amostral(v: Sequence[float]) -> float:
    if len(v) < 2:
        return 0.0
    m = _media(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def sharpe(retornos: Sequence[float], taxa_livre: float = 0.0) -> Optional[float]:
    """Sharpe anualizado. ``None`` quando nao ha dados para um numero honesto."""
    if len(retornos) < 2:
        return None
    excedente = [r - taxa_livre for r in retornos]
    desvio = _desvio_amostral(excedente)
    if desvio == 0:
        return None
    return _media(excedente) / desvio * math.sqrt(DIAS_DE_PREGAO_NO_ANO)


def sortino(retornos: Sequence[float], alvo: float = 0.0) -> Optional[float]:
    """Sortino anualizado: so a volatilidade das quedas conta como risco."""
    if len(retornos) < 2:
        return None
    excedente = [r - alvo for r in retornos]
    quedas = [min(r, 0.0) ** 2 for r in excedente]
    desvio_baixo = math.sqrt(_media(quedas))
    if desvio_baixo == 0:
        return None  # nenhum dia negativo: a razao seria infinita
    return _media(excedente) / desvio_baixo * math.sqrt(DIAS_DE_PREGAO_NO_ANO)


def exposicao(equity: Sequence[PontoEquity]) -> tuple[float, float]:
    """(% do tempo com posicao aberta, % medio do patrimonio alocado)."""
    if not equity:
        return 0.0, 0.0
    posicionado = sum(1 for p in equity if p.posicionado)
    tempo = posicionado / len(equity) * 100.0
    medias = [(p.exposicao / p.equity * 100.0) for p in equity if p.equity]
    return tempo, _media(medias)
