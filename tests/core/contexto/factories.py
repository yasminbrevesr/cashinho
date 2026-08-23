"""Series, fontes falsas e leituras para os testes de contexto."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence

from cashinho.core.contexto import (
    ConfigContexto,
    EstadoDaLeitura,
    FonteDeContexto,
    Instrumento,
    Leitura,
)
from cashinho.data.base import DataError
from cashinho.models import BRT, Candle, Series

ABERTURA = datetime(2026, 8, 21, 10, 0, tzinfo=BRT)


def serie(valores: Sequence[float], symbol: str = "TESTE", timeframe: str = "60m",
          inicio: Optional[datetime] = None, passo_min: int = 60) -> Series:
    inicio = inicio or ABERTURA
    candles = [
        Candle(inicio + timedelta(minutes=passo_min * i), v, v * 1.002, v * 0.998, v, 1000.0)
        for i, v in enumerate(valores)
    ]
    return Series(symbol, timeframe, candles)


def serie_de_dias(dias: int = 5, por_dia: int = 7, base: float = 100.0,
                  passo: float = 0.001, symbol: str = "TESTE") -> Series:
    """Serie com varios pregoes, um candle por hora."""
    candles = []
    preco = base
    dia = ABERTURA
    feitos = 0
    while feitos < dias:
        if dia.weekday() < 5:
            for i in range(por_dia):
                abertura = preco
                preco *= 1 + passo
                candles.append(Candle(dia + timedelta(minutes=60 * i), abertura,
                                      max(abertura, preco), min(abertura, preco),
                                      preco, 1000.0))
            feitos += 1
        dia = (dia + timedelta(days=1)).replace(hour=10, minute=0)
    return Series(symbol, "60m", candles)


def serie_ruidosa(n: int = 200, base: float = 100.0, amplitude: float = 0.004,
                  semente: int = 1, symbol: str = "TESTE") -> Series:
    """Serie deterministica com variacao - sem random, para o teste repetir."""
    valores = []
    preco = base
    x = semente
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        passo = ((x / 2147483648) - 0.5) * 2 * amplitude
        preco *= 1 + passo
        valores.append(preco)
    return serie(valores, symbol=symbol)


class FonteFalsa(FonteDeContexto):
    """Fonte controlada: devolve o que o teste mandar, ou o erro que ele pedir."""

    nome = "falsa"

    def __init__(self, series: Optional[Mapping[str, Series]] = None,
                 erros: Optional[Mapping[str, str]] = None, simulada: bool = False):
        self.series = dict(series or {})
        self.erros = dict(erros or {})
        self.simulada = simulada
        self.pedidos: list[str] = []

    def atende(self, instrumento: Instrumento) -> bool:
        return instrumento.chave in self.series or instrumento.chave in self.erros

    def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
        self.pedidos.append(instrumento.chave)
        if instrumento.chave in self.erros:
            raise DataError(self.erros[instrumento.chave])
        return self.series[instrumento.chave]


def leitura(instrumento: Instrumento, variacao: Optional[float] = 1.0,
            estado: EstadoDaLeitura = EstadoDaLeitura.OK, ultimo: float = 100.0,
            **campos) -> Leitura:
    return Leitura(instrumento=instrumento, estado=estado, ultimo=ultimo,
                   variacao_pct=variacao, fonte="falsa", **campos)


def config(**campos) -> ConfigContexto:
    base = dict(instrumentos=("ibovespa", "dolar", "minerio"), dias=10)
    base.update(campos)
    return ConfigContexto(**base)
