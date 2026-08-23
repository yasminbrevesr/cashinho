"""Provedor de dados via Yahoo Finance (yfinance).

E' a fonte gratuita mais pratica para acoes da B3: basta somar ``.SA`` ao
ticker (PETR4 -> PETR4.SA). Os dados intradiarios tem atraso de ~15 minutos
no Yahoo, entao o robo trata isso como uma segunda opiniao sobre o candle
anterior, e nao como book em tempo real. Para dados sem atraso, implemente um
Provider apontando para o feed da sua corretora (ver README).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from ..models import BRT, Candle, Series
from .base import DataError, Provider
from .cache import Cache

_MAX_DIAS_INTRADAY = {"1m": 7, "2m": 59, "5m": 59, "15m": 59, "30m": 59, "60m": 729, "1h": 729}


def sufixo_b3(symbol: str) -> str:
    """PETR4 -> PETR4.SA; o que ja e' ticker do Yahoo passa intacto.

    Passam intactos: indices (``^BVSP``), tickers com ponto (``PETR4.SA``),
    cambio (``USDBRL=X``) e futuros (``BZ=F``). Somar ``.SA`` a esses ultimos
    produzia ``USDBRL=X.SA``, que nao existe - o download voltava vazio e o
    ativo sumia da leitura sem que ninguem entendesse por que.
    """
    s = symbol.strip().upper()
    if "." in s or s.startswith("^") or "=" in s:
        return s
    return f"{s}.SA"


class YahooProvider(Provider):
    nome = "yahoo"

    def __init__(self, ttl_segundos: int = 45, cache: Optional[Cache] = None):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:  # pragma: no cover - depende do ambiente
            raise DataError(
                "yfinance nao instalado. Rode: pip install -r requirements.txt "
                "ou use --fonte demo/csv."
            ) from e
        self.cache = cache or Cache(ttl_segundos=ttl_segundos)

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        import yfinance as yf

        ticker = sufixo_b3(symbol)
        dias = min(dias, _MAX_DIAS_INTRADAY.get(timeframe, 729))
        chave = f"{ticker}-{timeframe}-{dias}"
        em_cache = self.cache.obter(chave)
        if em_cache is not None:
            return em_cache

        intervalo = "60m" if timeframe == "1h" else timeframe
        periodo = f"{max(dias, 1)}d"
        try:
            df = yf.download(
                ticker,
                period=periodo,
                interval=intervalo,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as e:  # pragma: no cover - depende da rede
            raise DataError(f"falha ao baixar {ticker}: {e}") from e

        if df is None or len(df) == 0:
            raise DataError(f"sem dados para {ticker} ({timeframe})")

        candles: list[Candle] = []
        for ts, linha in df.iterrows():
            try:
                o = float(_valor(linha, "Open", ticker))
                h = float(_valor(linha, "High", ticker))
                l = float(_valor(linha, "Low", ticker))
                c = float(_valor(linha, "Close", ticker))
                v = float(_valor(linha, "Volume", ticker) or 0.0)
                if any(x != x for x in (o, h, l, c)):  # NaN
                    continue
                dt = ts.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=BRT)
                # a validacao do Candle mora no proprio Candle: linha
                # incoerente (maxima abaixo da minima, preco zerado) e'
                # descartada aqui, e nao vira serie
                candles.append(Candle(dt.astimezone(BRT), o, h, l, c, v))
            except (TypeError, ValueError):
                continue

        if not candles:
            raise DataError(f"sem candles validos para {ticker} ({timeframe})")
        serie = Series(symbol.upper(), timeframe, candles)
        self.cache.guardar(chave, serie)
        return serie


def _valor(linha, campo: str, ticker: str):
    """Le uma coluna do DataFrame, lidando com o MultiIndex do yfinance."""
    try:
        return linha[campo]
    except KeyError:
        pass
    try:
        return linha[(campo, ticker)]
    except (KeyError, TypeError):
        return None
