"""Provedor sintetico: pregoes reproduziveis, sem depender de rede.

Serve para exercitar o robo e a pagina de backtest quando nao ha dados reais
a mao. Os precos vem de um gerador com semente fixa - a mesma semente sempre
produz a mesma serie -, com um regime sorteado por dia (alta, baixa ou
lateral). Nao e' mercado: e' um simulador de forma, util para testar o
sistema, inutil para tirar conclusao sobre estrategia.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Optional

from ..core.mtf.session import SESSAO_B3, Sessao
from ..models import BRT, Candle, Series
from .base import Provider, minutos_do_timeframe

REGIMES = {
    "alta": 0.00008,
    "baixa": -0.00007,
    "lateral": 0.0,
}


class SyntheticProvider(Provider):
    """Gera candles deterministicos para um ativo ficticio."""

    nome = "demo"

    def __init__(
        self,
        semente: int = 42,
        preco_inicial: float = 30.0,
        volatilidade: float = 0.0008,
        sessao: Sessao = SESSAO_B3,
        dias: int = 10,
        fim: Optional[date] = None,
    ):
        self.semente = semente
        self.preco_inicial = preco_inicial
        self.volatilidade = volatilidade
        self.sessao = sessao
        self.dias_padrao = dias
        self.fim = fim or date(2026, 8, 21)

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        minutos = minutos_do_timeframe(timeframe)
        rnd = random.Random(f"{self.semente}-{symbol.upper()}")
        pregoes = self._dias_uteis(dias or self.dias_padrao)

        preco = self.preco_inicial
        candles: list[Candle] = []
        for dia in pregoes:
            abre, fecha = self.sessao.limites(dia)
            passos = int((fecha - abre).total_seconds() // 60 // minutos)
            deriva = REGIMES[rnd.choice(list(REGIMES))] * minutos
            for i in range(passos):
                abertura = preco
                preco = preco * (1 + rnd.gauss(deriva, self.volatilidade * (minutos ** 0.5)))
                topo = max(abertura, preco) * (1 + abs(rnd.gauss(0, 0.0004)))
                base = min(abertura, preco) * (1 - abs(rnd.gauss(0, 0.0004)))
                candles.append(
                    Candle(
                        ts=abre + timedelta(minutes=i * minutos),
                        open=round(abertura, 2),
                        high=round(topo, 2),
                        low=round(base, 2),
                        close=round(preco, 2),
                        volume=float(int(rnd.uniform(5_000, 60_000))),
                    )
                )
        return Series(symbol.upper(), timeframe, candles)

    def _dias_uteis(self, quantos: int) -> list[date]:
        dias: list[date] = []
        dia = self.fim
        while len(dias) < quantos:
            if self.sessao.eh_dia_util(dia):
                dias.append(dia)
            dia -= timedelta(days=1)
        return sorted(dias)
