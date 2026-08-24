"""Monta os provedores a partir da configuracao - e so os implementados.

Provedor que ainda nao existe (MetaTrader) aparece como **conhecido mas nao
implementado**, com a mensagem dizendo isso. Nunca some da lista em silencio,
e nunca e' substituido por outro parecido.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..settings import ConfigMarketData, carregar
from .base import DataError, Provider
from .servico import MarketDataService

# nome na configuracao -> como construir. Quem nao esta aqui nao existe ainda.
IMPLEMENTADOS: dict[str, str] = {
    "demo": "pregoes sinteticos reproduziveis (nao sao precos reais)",
    "csv": "arquivos locais em dados/",
    "brapi": "brapi.dev - historico e cotacao com o atraso do plano",
    "yahoo": "Yahoo Finance via yfinance (atraso tipico de ~15 min)",
}
PLANEJADOS: dict[str, str] = {
    "metatrader": "MetaTrader 5 / Genial - previsto, ainda nao implementado",
}


class ProvedorDesconhecidoError(DataError):
    """Pediram um provedor que o Cashinho nao conhece ou ainda nao tem."""


def construir(nome: str, config: Optional[ConfigMarketData] = None,
              **extra) -> Provider:
    """Constroi um provedor pelo nome declarado na configuracao."""
    chave = (nome or "").strip().lower()
    cfg = config or carregar()

    if chave in PLANEJADOS:
        raise ProvedorDesconhecidoError(
            f"provedor '{chave}' esta previsto mas ainda nao implementado: "
            f"{PLANEJADOS[chave]}. Configure outro provedor ou deixe a finalidade "
            "sem provedor - o Cashinho prefere recusar a improvisar")
    if chave not in IMPLEMENTADOS:
        disponiveis = ", ".join(sorted(IMPLEMENTADOS))
        raise ProvedorDesconhecidoError(
            f"provedor desconhecido: '{chave}' (implementados: {disponiveis})")

    if chave == "demo":
        from .synthetic import SyntheticProvider

        return SyntheticProvider(**extra)
    if chave == "csv":
        from .csv_provider import CSVProvider

        return CSVProvider(**extra)
    if chave == "yahoo":
        from .yahoo import YahooProvider

        return YahooProvider(**extra)

    from .brapi import BrapiMarketDataProvider

    return BrapiMarketDataProvider(cfg, **extra)


def montar_servico(config: Optional[ConfigMarketData] = None,
                   log=None, **extra) -> MarketDataService:
    """O servico completo, com os dois papeis resolvidos pela configuracao."""
    cfg = config or carregar()

    historico = construir(cfg.historico, cfg, **extra) if cfg.historico else None
    tempo_real = None
    if cfg.tem_tempo_real:
        # provedor de tempo real que nao existe NAO vira historico disfarcado:
        # o erro sobe, e quem configurou fica sabendo
        tempo_real = construir(cfg.tempo_real, cfg, **extra)

    return MarketDataService(historico=historico, tempo_real=tempo_real, log=log)


def catalogo() -> dict[str, dict]:
    """O que aparece na tela de configuracao."""
    saida = {n: {"descricao": d, "disponivel": True} for n, d in IMPLEMENTADOS.items()}
    saida.update({n: {"descricao": d, "disponivel": False} for n, d in PLANEJADOS.items()})
    return saida
