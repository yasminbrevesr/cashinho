"""Provedores falsos e respostas simuladas para os testes de market data."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Sequence

from cashinho.data.base import DataError
from cashinho.data.mercado import MarketDataProvider
from cashinho.data.status import Capacidades
from cashinho.models import BRT, Candle, Series
from cashinho.settings import ConfigMarketData

AGORA = datetime(2026, 8, 21, 14, 0, tzinfo=BRT)


def serie(n: int = 30, symbol: str = "PETR4", timeframe: str = "1d",
          inicio: Optional[datetime] = None, passo_min: int = 60 * 24,
          preco: float = 30.0) -> Series:
    comeco = inicio or (AGORA - timedelta(minutes=passo_min * n))
    candles = []
    for i in range(n):
        p = preco * (1 + 0.001 * i)
        candles.append(Candle(comeco + timedelta(minutes=passo_min * i),
                              p, p * 1.005, p * 0.995, p * 1.002, 1_000_000.0))
    return Series(symbol, timeframe, candles)


class ProviderFalso(MarketDataProvider):
    """Provedor controlado: devolve o que o teste mandar."""

    def __init__(self, nome: str = "falso", series: Optional[Series] = None,
                 erro: str = "", capacidades: Optional[Capacidades] = None,
                 cotacao=None):
        self.nome = nome
        self._serie = series
        self._erro = erro
        self._cotacao = cotacao
        self.capacidades = capacidades or Capacidades(
            candles_historicos=True, timeframes=("1m", "5m", "1d"))
        self.chamadas = 0

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        self.chamadas += 1
        if self._erro:
            raise DataError(self._erro)
        return self._serie if self._serie is not None else serie(timeframe=timeframe)

    def cotacao(self, symbol: str):
        if self._cotacao is not None:
            return self._cotacao
        return super().cotacao(symbol)


def provider_tempo_real(nome: str = "mt5", atraso_s: float = 0.2, **campos):
    """Um provedor que declara tudo o que day trade exige."""
    return ProviderFalso(nome=nome, capacidades=Capacidades(
        candles_historicos=True, cotacao=True, cotacao_em_tempo_real=True,
        ticks_em_tempo_real=True, livro_de_ofertas=True, intradiario_1m=True,
        timeframes=("1m", "5m", "15m", "1d"), atraso_tipico_s=atraso_s), **campos)


def config_brapi(**campos) -> ConfigMarketData:
    base = dict(brapi_token="token-de-teste", brapi_atraso_s=900.0,
                brapi_timeframes=("1d",))
    base.update(campos)
    return ConfigMarketData(**base)


def resposta_brapi(historico: int = 5, momento: Optional[datetime] = None,
                   **campos) -> str:
    quando = momento or (AGORA - timedelta(minutes=15))
    resultado: dict[str, Any] = {
        "symbol": "PETR4",
        "regularMarketPrice": 38.42,
        "regularMarketOpen": 38.0,
        "regularMarketDayHigh": 38.6,
        "regularMarketDayLow": 37.9,
        "regularMarketPreviousClose": 37.8,
        "regularMarketVolume": 41_000_000,
        "regularMarketTime": quando.isoformat(),
        "historicalDataPrice": [
            {"date": int((AGORA - timedelta(days=d)).timestamp()),
             "open": 38.0, "high": 38.6, "low": 37.9, "close": 38.4,
             "volume": 4e7}
            for d in range(historico, 0, -1)
        ],
    }
    resultado.update(campos)
    return json.dumps({"results": [resultado]})


def abridor(corpo: str, registro: Optional[list] = None, codigo: int = 200):
    """Simula a chamada HTTP, guardando as URLs pedidas.

    Devolve o par ``(codigo, corpo)`` - o mesmo que o urllib produz -, para os
    testes exercitarem 401, 404, 429 e 500 pelo caminho de codigo real.
    """
    def abrir(url: str, cabecalhos: Mapping[str, str]) -> tuple[int, str]:
        if registro is not None:
            registro.append((url, dict(cabecalhos)))
        return codigo, corpo
    return abrir


def resposta_v2(historico: int = 5, momento: Optional[datetime] = None,
                **campos) -> str:
    """A forma da v2: os campos aninhados em ``results[0].data``."""
    interno = json.loads(resposta_brapi(historico, momento, **campos))
    return json.dumps({"results": [{"data": interno["results"][0]}]})
