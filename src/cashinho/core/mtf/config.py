"""Configuracao da combinacao de timeframes.

A combinacao NAO e' fixa no codigo: os papeis (contexto, tendencia, setup,
gatilho) e os timeframes de cada um vem daqui, e podem ser trocados por
configuracao - inclusive com mais ou menos camadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from .errors import ConfiguracaoInvalidaError
from .session import SESSAO_B3, Sessao
from .timeframes import Timeframe, parse_timeframe

CAMADAS_PADRAO: dict[str, str] = {
    "contexto": "60m",
    "tendencia": "15m",
    "setup": "5m",
    "gatilho": "1m",
}


@dataclass(frozen=True)
class MTFConfig:
    """Quais timeframes o robo olha e para que serve cada um.

    ``camadas`` mapeia um papel para um timeframe. O papel e' so um nome:
    voce pode usar ``{"macro": "1d", "diretor": "30m", "gatilho": "2m"}`` sem
    tocar em uma linha de codigo.
    """

    base: str = "1m"
    camadas: Mapping[str, str] = field(default_factory=lambda: dict(CAMADAS_PADRAO))
    sessao: Sessao = SESSAO_B3
    rotulagem: str = "abertura"  # "abertura" ou "fechamento"
    descartar_fora_da_sessao: bool = True

    def __post_init__(self) -> None:
        if not self.camadas:
            raise ConfiguracaoInvalidaError("configure ao menos uma camada de timeframe")
        if self.rotulagem not in ("abertura", "fechamento"):
            raise ConfiguracaoInvalidaError(
                f"rotulagem invalida: {self.rotulagem!r} (use 'abertura' ou 'fechamento')"
            )
        tf_base = parse_timeframe(self.base)
        resolvidas: dict[str, Timeframe] = {}
        for papel, valor in self.camadas.items():
            tf = parse_timeframe(valor)
            if not tf.eh_multiplo_de(tf_base):
                raise ConfiguracaoInvalidaError(
                    f"camada '{papel}' ({tf.rotulo}) nao e' multiplo do timeframe base "
                    f"({tf_base.rotulo}); o robo nao pode inventar candles que nao existem"
                )
            resolvidas[papel] = tf
        object.__setattr__(self, "_tf_base", tf_base)
        object.__setattr__(self, "_resolvidas", resolvidas)
        object.__setattr__(self, "camadas", {p: t.rotulo for p, t in resolvidas.items()})

    # ------------------------------------------------------------------
    @property
    def tf_base(self) -> Timeframe:
        return getattr(self, "_tf_base")

    def timeframe(self, papel: str) -> Timeframe:
        try:
            return getattr(self, "_resolvidas")[papel]
        except KeyError as e:
            disponiveis = ", ".join(sorted(self.camadas))
            raise ConfiguracaoInvalidaError(
                f"camada '{papel}' nao configurada (disponiveis: {disponiveis})"
            ) from e

    def papeis(self) -> list[str]:
        """Papeis do maior para o menor timeframe (contexto -> gatilho)."""
        resolvidas: dict[str, Timeframe] = getattr(self, "_resolvidas")
        minutos_sessao = self.sessao.duracao_minutos()
        return sorted(
            resolvidas,
            key=lambda p: -resolvidas[p].duracao_minutos(minutos_sessao),
        )

    def timeframes(self) -> list[str]:
        """Rotulos unicos, do maior para o menor, incluindo o timeframe base."""
        resolvidas: dict[str, Timeframe] = getattr(self, "_resolvidas")
        minutos_sessao = self.sessao.duracao_minutos()
        rotulos = {t.rotulo: t for t in resolvidas.values()}
        rotulos.setdefault(self.tf_base.rotulo, self.tf_base)
        return sorted(rotulos, key=lambda r: -rotulos[r].duracao_minutos(minutos_sessao))

    @property
    def gatilho(self) -> str:
        """Papel de menor timeframe - onde a decisao acontece."""
        return self.papeis()[-1]

    @property
    def contexto(self) -> str:
        """Papel de maior timeframe."""
        return self.papeis()[0]

    def papel_de(self, timeframe: str) -> Optional[str]:
        alvo = parse_timeframe(timeframe).rotulo
        for papel in self.papeis():
            if self.timeframe(papel).rotulo == alvo:
                return papel
        return None

    # ------------------------------------------------------------------
    @classmethod
    def padrao(cls) -> "MTFConfig":
        """60m contexto / 15m tendencia / 5m setup / 1m gatilho."""
        return cls()

    @classmethod
    def de_dict(cls, dados: Mapping[str, object]) -> "MTFConfig":
        """Constroi a partir de um dicionario (arquivo de configuracao)."""
        sessao = dados.get("sessao", SESSAO_B3)
        if isinstance(sessao, Mapping):
            from datetime import time as _time

            def _hora(v, padrao):
                if v is None:
                    return padrao
                if isinstance(v, _time):
                    return v
                h, m = str(v).split(":")[:2]
                return _time(int(h), int(m))

            sessao = Sessao(
                abertura=_hora(sessao.get("abertura"), SESSAO_B3.abertura),
                fechamento=_hora(sessao.get("fechamento"), SESSAO_B3.fechamento),
            )
        camadas = dados.get("camadas") or dict(CAMADAS_PADRAO)
        return cls(
            base=str(dados.get("base", "1m")),
            camadas=dict(camadas),  # type: ignore[arg-type]
            sessao=sessao,  # type: ignore[arg-type]
            rotulagem=str(dados.get("rotulagem", "abertura")),
            descartar_fora_da_sessao=bool(dados.get("descartar_fora_da_sessao", True)),
        )

    def para_dict(self) -> dict[str, object]:
        return {
            "base": self.tf_base.rotulo,
            "camadas": dict(self.camadas),
            "rotulagem": self.rotulagem,
            "descartar_fora_da_sessao": self.descartar_fora_da_sessao,
            "sessao": {
                "abertura": self.sessao.abertura.strftime("%H:%M"),
                "fechamento": self.sessao.fechamento.strftime("%H:%M"),
            },
        }
