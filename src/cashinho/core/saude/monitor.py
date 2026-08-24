"""O monitor: roda as sondas e monta o retrato - com a regra de bloqueio.

A regra que da nome ao modulo: **Market Data fora do ar ou desatualizado
bloqueia operacao nova**. Ela mora aqui, em uma lista explicita de motivos, e
nao em um `if` escondido dentro de uma tela.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Sequence

from ...models import BRT
from .estados import EstadoDeSaude, Modo
from .modelos import COMPONENTES, Componente, SaudeDoSistema
from .sondas import (
    LimiaresSaude,
    Sonda,
    SondaBanco,
    SondaBroker,
    SondaMarketData,
    SondaNoticias,
    SondaPorTelemetria,
    SondaRisco,
)
from .telemetria import Telemetria

MARCO_ANALISE = "analise"


@dataclass(frozen=True)
class KillSwitchDoBroker:
    """A trava acionada no Paper Broker, no formato que o painel espera."""

    motivo: str
    codigo: str = "paper_broker"

    def para_dict(self) -> dict:
        return {"codigo": self.codigo, "motivo": self.motivo}


@dataclass(frozen=True)
class ConfigSaude:
    """O que derruba as operacoes novas."""

    # estados de um componente critico que bloqueiam operacao nova.
    # DEGRADED fica de fora por padrao: dado com pequeno atraso e' o normal em
    # feed gratuito, e bloquear nele travaria o robo o tempo todo
    bloqueia_em: tuple[EstadoDeSaude, ...] = (EstadoDeSaude.OFFLINE,)
    kill_switch_bloqueia: bool = True
    limiares: LimiaresSaude = field(default_factory=LimiaresSaude)

    def para_dict(self) -> dict:
        return {
            "bloqueia_em": [e.value for e in self.bloqueia_em],
            "kill_switch_bloqueia": self.kill_switch_bloqueia,
            "limiares": self.limiares.para_dict(),
        }


class MonitorDeSaude:
    """Junta as sondas e responde: da para operar agora?"""

    def __init__(
        self,
        telemetria: Optional[Telemetria] = None,
        config: Optional[ConfigSaude] = None,
        sondas: Optional[Sequence[Sonda]] = None,
        modo: Modo = Modo.ANALISE,
        risco=None,
        broker=None,
        noticias=None,
        banco=None,
        market_data=None,
        relogio: Optional[Callable[[], datetime]] = None,
    ):
        self.telemetria = telemetria or Telemetria()
        self.config = config or ConfigSaude()
        self.modo = modo
        self.risco = risco
        self.broker = broker
        self.market_data = market_data
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self.sondas: list[Sonda] = list(sondas) if sondas is not None else self._padrao(
            risco=risco, broker=broker, noticias=noticias, banco=banco,
            market_data=market_data)

    # ------------------------------------------------------------------
    def _padrao(self, risco=None, broker=None, noticias=None, banco=None,
                market_data=None) -> list[Sonda]:
        """As sete sondas do painel, na ordem da tela."""
        lim = self.config.limiares
        t = self.telemetria
        return [
            SondaMarketData(t, lim, servico=market_data),
            SondaBanco(banco, t, lim) if banco else
            SondaPorTelemetria("database", t, lim),
            SondaPorTelemetria("scanner", t, lim, opcional=True),
            SondaBroker(broker, t, lim),
            SondaNoticias(noticias, t, lim),
            SondaPorTelemetria("backtest", t, lim, opcional=True),
            SondaRisco(risco, t, lim),
        ]

    # ------------------------------------------------------------------
    def verificar(self, instante: Optional[datetime] = None) -> SaudeDoSistema:
        agora = instante or self._relogio()
        componentes = tuple(s.verificar(agora) for s in self.sondas)
        kill_switch = self._kill_switch()

        return SaudeDoSistema(
            timestamp=agora,
            componentes=componentes,
            modo=self.modo,
            kill_switch=kill_switch,
            ultima_analise=self.telemetria.ultimo_marco(MARCO_ANALISE),
            bloqueios=self._bloqueios(componentes, kill_switch),
            market_data=self.market_data,
        )

    def permite_novas_operacoes(self, instante: Optional[datetime] = None) -> bool:
        return not self.verificar(instante).bloqueia_novas_operacoes

    def registrar_analise(self, quando: Optional[datetime] = None) -> datetime:
        """Marca o horario da ultima analise - o que a tela mostra."""
        return self.telemetria.marco(MARCO_ANALISE, quando)

    # ------------------------------------------------------------------
    def _kill_switch(self):
        """A trava, venha ela do Risk Manager ou do botao do Paper Broker.

        Sao dois lugares diferentes que param o robo, e o painel que mostrasse
        so um deles estaria mentindo na metade das vezes.
        """
        if self.risco is not None:
            do_risco = getattr(self.risco.status(), "kill_switch", None)
            if do_risco is not None:
                return do_risco
        if self.broker is not None and getattr(self.broker, "kill_switch_ativo", False):
            return KillSwitchDoBroker(
                getattr(self.broker, "kill_switch_motivo", "") or "acionado no Paper Broker")
        return None

    def _bloqueios(self, componentes: Sequence[Componente], kill_switch) -> tuple[str, ...]:
        motivos: list[str] = []
        for c in componentes:
            if c.critico and c.estado in self.config.bloqueia_em:
                motivos.append(f"{c.nome} {c.estado.value}: {c.detalhe}")
        if kill_switch is not None and self.config.kill_switch_bloqueia:
            motivos.append(f"KILL SWITCH acionado: {getattr(kill_switch, 'motivo', '')}")
        return tuple(motivos)
