"""Os objetos do painel: componente e retrato do sistema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from .estados import EstadoDeSaude, Modo, pior_de
from .telemetria import RegistroDeErro

# os sete componentes do painel, na ordem em que aparecem
COMPONENTES = (
    ("market_data", "Market Data"),
    ("database", "Database"),
    ("scanner", "Scanner"),
    ("paper_broker", "Paper Broker"),
    ("news", "News"),
    ("backtest", "Backtest Engine"),
    ("risk_manager", "Risk Manager"),
)

NOMES = dict(COMPONENTES)


@dataclass(frozen=True)
class Componente:
    """A saude de uma peca do sistema."""

    chave: str
    nome: str
    estado: EstadoDeSaude
    detalhe: str = ""
    ultimo_timestamp: Optional[datetime] = None   # do dado recebido
    latencia_ms: Optional[float] = None
    erros: tuple[RegistroDeErro, ...] = ()
    modo: str = ""
    # componente critico derruba as operacoes novas quando cai
    critico: bool = False

    def idade_em(self, instante: datetime) -> Optional[float]:
        if self.ultimo_timestamp is None:
            return None
        return (instante - self.ultimo_timestamp).total_seconds() / 60

    @property
    def n_erros(self) -> int:
        return len(self.erros)

    def para_dict(self) -> dict:
        return {
            "chave": self.chave,
            "nome": self.nome,
            "estado": self.estado.value,
            "detalhe": self.detalhe,
            "ultimo_timestamp": (self.ultimo_timestamp.isoformat()
                                 if self.ultimo_timestamp else None),
            "latencia_ms": None if self.latencia_ms is None else round(self.latencia_ms, 1),
            "erros": [e.para_dict() for e in self.erros],
            "modo": self.modo,
            "critico": self.critico,
        }


@dataclass(frozen=True)
class SaudeDoSistema:
    """O retrato do sistema em um instante - o que a tela mostra."""

    timestamp: datetime
    componentes: tuple[Componente, ...]
    modo: Modo = Modo.ANALISE
    kill_switch: Optional[object] = None
    ultima_analise: Optional[datetime] = None
    bloqueios: tuple[str, ...] = ()   # por que operacoes novas estao barradas

    # -- consultas ------------------------------------------------------
    def componente(self, chave: str) -> Optional[Componente]:
        for c in self.componentes:
            if c.chave == chave:
                return c
        return None

    @property
    def estado_geral(self) -> EstadoDeSaude:
        return pior_de(c.estado for c in self.componentes)

    @property
    def criticos_fora(self) -> tuple[Componente, ...]:
        return tuple(c for c in self.componentes if c.critico and not c.estado.saudavel)

    @property
    def kill_switch_ativo(self) -> bool:
        return self.kill_switch is not None

    @property
    def bloqueia_novas_operacoes(self) -> bool:
        """Da para abrir operacao nova agora?

        Nao e' opiniao do painel: e' a lista ``bloqueios``, montada pelo
        monitor a partir de regras explicitas.
        """
        return bool(self.bloqueios)

    @property
    def rotulo_operacao(self) -> str:
        return ("OPERACOES BLOQUEADAS" if self.bloqueia_novas_operacoes
                else "OPERACOES LIBERADAS")

    @property
    def erros(self) -> tuple[RegistroDeErro, ...]:
        todos = [e for c in self.componentes for e in c.erros]
        return tuple(sorted(todos, key=lambda e: e.quando, reverse=True))

    def para_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "estado_geral": self.estado_geral.value,
            "modo": self.modo.value,
            "kill_switch": _kill_switch_dict(self.kill_switch),
            "ultima_analise": self.ultima_analise.isoformat() if self.ultima_analise else None,
            "bloqueia_novas_operacoes": self.bloqueia_novas_operacoes,
            "bloqueios": list(self.bloqueios),
            "componentes": [c.para_dict() for c in self.componentes],
        }


def _kill_switch_dict(ks) -> Optional[dict]:
    if ks is None:
        return None
    if hasattr(ks, "para_dict"):
        return ks.para_dict()
    return {"motivo": str(ks)}
