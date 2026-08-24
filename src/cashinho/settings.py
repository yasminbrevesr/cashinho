"""Configuracao por ambiente - sem dependencia, sem token no codigo.

Le variaveis do ambiente e, se existir, de um arquivo ``.env`` na raiz do
projeto. O ``.env`` **nunca** vai para o repositorio; o que vai e' o
``.env.example``, sem valor nenhum preenchido.

Nao ha biblioteca de configuracao aqui de proposito: o projeto e' stdlib puro,
e ler `CHAVE=valor` de um arquivo cabe em vinte linhas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = RAIZ / ".env"


def carregar_env(caminho: Optional[Path] = None) -> dict[str, str]:
    """Le um arquivo ``.env`` simples. Ausente devolve vazio, sem reclamar."""
    origem = Path(caminho) if caminho else ARQUIVO_ENV
    if not origem.exists():
        return {}
    valores: dict[str, str] = {}
    for linha in origem.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valor = valor.strip().strip('"').strip("'")
        valores[chave.strip()] = valor
    return valores


def valor(chave: str, padrao: str = "", ambiente: Optional[Mapping[str, str]] = None) -> str:
    """Ambiente tem prioridade sobre o ``.env``; ``.env`` sobre o padrao."""
    if ambiente is not None:
        return str(ambiente.get(chave, padrao))
    do_processo = os.environ.get(chave)
    if do_processo is not None:
        return do_processo
    return carregar_env().get(chave, padrao)


def numero(chave: str, padrao: Optional[float] = None,
           ambiente: Optional[Mapping[str, str]] = None) -> Optional[float]:
    """Numero da configuracao. Texto invalido vira o padrao, nao excecao."""
    bruto = valor(chave, "", ambiente)
    if not bruto.strip():
        return padrao
    try:
        return float(bruto)
    except ValueError:
        return padrao


@dataclass(frozen=True)
class ConfigMarketData:
    """Qual provedor serve cada finalidade, e com que credencial."""

    historico: str = "demo"
    tempo_real: str = ""          # vazio = nao configurado
    brapi_token: str = ""
    brapi_base_url: str = "https://brapi.dev/api"
    # atraso declarado do plano contratado, em segundos. Sem isto, o provedor
    # nao sabe se serve para tempo real - e assume que NAO serve
    brapi_atraso_s: Optional[float] = None
    brapi_timeframes: tuple[str, ...] = ()
    brapi_requisicoes_por_minuto: Optional[float] = None

    @property
    def tem_tempo_real(self) -> bool:
        return bool(self.tempo_real.strip())

    @property
    def brapi_autenticado(self) -> bool:
        return bool(self.brapi_token.strip())

    def para_dict(self) -> dict:
        return {
            "historico": self.historico,
            "tempo_real": self.tempo_real or None,
            "brapi_base_url": self.brapi_base_url,
            "brapi_autenticado": self.brapi_autenticado,
            "brapi_atraso_s": self.brapi_atraso_s,
            "brapi_timeframes": list(self.brapi_timeframes),
            "brapi_requisicoes_por_minuto": self.brapi_requisicoes_por_minuto,
        }


def carregar(ambiente: Optional[Mapping[str, str]] = None) -> ConfigMarketData:
    """Monta a configuracao de market data a partir do ambiente/.env."""
    timeframes = tuple(
        t.strip() for t in valor("BRAPI_TIMEFRAMES", "", ambiente).split(",") if t.strip()
    )
    return ConfigMarketData(
        historico=valor("MARKET_DATA_HISTORICAL_PROVIDER", "demo", ambiente).strip().lower(),
        tempo_real=valor("MARKET_DATA_REALTIME_PROVIDER", "", ambiente).strip().lower(),
        brapi_token=valor("BRAPI_TOKEN", "", ambiente),
        brapi_base_url=valor("BRAPI_BASE_URL", "https://brapi.dev/api", ambiente).rstrip("/"),
        brapi_atraso_s=numero("BRAPI_ATRASO_SEGUNDOS", None, ambiente),
        brapi_timeframes=timeframes,
        brapi_requisicoes_por_minuto=numero("BRAPI_REQUISICOES_POR_MINUTO", None, ambiente),
    )
