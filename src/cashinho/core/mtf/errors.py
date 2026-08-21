"""Erros do motor multi-timeframe."""

from __future__ import annotations


class MTFError(RuntimeError):
    """Erro generico do motor multi-timeframe."""


class LookaheadError(MTFError):
    """Tentativa de ler um candle que ainda nao fechou.

    E' o erro mais importante do modulo: se o robo consultasse o candle de 60m
    em formacao enquanto decide no 1m, ele estaria usando informacao que so
    existira no futuro - o backtest ficaria otimista e o resultado ao vivo,
    nao. Por isso a leitura falha alto em vez de devolver o candle parcial.
    """


class DadosInsuficientesError(MTFError):
    """Nao ha candles suficientes para responder a consulta."""


class ConfiguracaoInvalidaError(MTFError):
    """Combinacao de timeframes invalida."""
