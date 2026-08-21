"""Excecoes do dominio.

Erros explicitos e tipados: cada um representa uma regra do Cashinho
que foi violada, e nao uma falha generica de programacao.
"""

from __future__ import annotations


class CashinhoError(Exception):
    """Base de todos os erros do Cashinho."""


class UnclosedCandleError(CashinhoError):
    """Uso de candle ainda nao fechado onde a regra exige fechamento.

    Levantado pelos indicadores e pelo motor multi-timeframe.
    """


class LookaheadError(CashinhoError):
    """Tentativa de acessar dado posterior ao instante logico do sistema.

    Levantado quando uma serie contem candles com fechamento no futuro
    em relacao ao Clock ativo.
    """


class DataQualityBlockedError(CashinhoError):
    """Portao de qualidade de dados bloqueou a analise."""


class ModeNotAllowedError(CashinhoError):
    """Operacao incompativel com o modo ativo.

    Usado, entre outros casos, para impedir o modo LIVE enquanto os
    mecanismos de seguranca nao estiverem implementados e testados.
    """


class RiskRejectionError(CashinhoError):
    """Risk Manager rejeitou a operacao.

    Nenhuma estrategia pode capturar este erro para prosseguir.
    """
