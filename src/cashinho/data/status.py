"""Estado do dado e capacidades do provedor.

Duas perguntas que o resto do sistema precisa responder **antes** de usar um
numero: "este dado esta atual o bastante para o que eu vou fazer com ele?" e
"este provedor sabe fazer o que eu preciso?".

Nenhuma das duas tem resposta universal. Um candle diario de 40 minutos atras
esta perfeito; um candle de 1m de 40 minutos atras esta morto. Por isso o
limite de "velho" nao e' uma constante do modulo - ele vem do provedor e do
timeframe.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class StatusDados(str, Enum):
    """O estado do dado que acabou de chegar."""

    ONLINE = "ONLINE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"

    @property
    def rotulo(self) -> str:
        return self.value

    @property
    def descricao(self) -> str:
        return {
            "ONLINE": "dado dentro da idade esperada para este provedor",
            "DELAYED": "provedor entrega com atraso conhecido e declarado",
            "STALE": "deveria estar atualizado, mas parou de atualizar",
            "DEGRADED": "provedor respondendo parcialmente",
            "OFFLINE": "nao foi possivel obter dado",
        }[self.value]

    @property
    def peso(self) -> int:
        return {"ONLINE": 0, "DELAYED": 1, "DEGRADED": 2, "STALE": 3, "OFFLINE": 4}[self.value]

    @property
    def tem_dado(self) -> bool:
        """Chegou numero? DELAYED e STALE chegaram - so nao servem para tudo."""
        return self is not StatusDados.OFFLINE

    @property
    def serve_para_tempo_real(self) -> bool:
        """So ONLINE serve para decidir entrada agora.

        DELAYED nao serve **por definicao**: um dado que o proprio provedor
        declara atrasado nunca pode ser apresentado como cotacao do momento.
        """
        return self is StatusDados.ONLINE

    @property
    def aviso(self) -> str:
        """A frase que a tela mostra. Vazia quando nao ha o que avisar."""
        return {
            "ONLINE": "",
            "DELAYED": "DADOS ATRASADOS - NAO UTILIZAR PARA ENTRADA EM TEMPO REAL",
            "STALE": "DADO PAROU DE ATUALIZAR - NAO UTILIZAR PARA ENTRADA EM TEMPO REAL",
            "DEGRADED": "PROVEDOR DEGRADADO - confira a cobertura antes de decidir",
            "OFFLINE": "SEM DADOS",
        }[self.value]


def pior_status(*estados: Optional[StatusDados]) -> StatusDados:
    """O pior estado do conjunto. Vazio conta como OFFLINE."""
    conhecidos = [e for e in estados if e is not None]
    if not conhecidos:
        return StatusDados.OFFLINE
    return max(conhecidos, key=lambda e: e.peso)


@dataclass(frozen=True)
class Capacidades:
    """O que o provedor sabe fazer - declarado, nunca deduzido.

    A pergunta nao e' "sera que da certo?" e sim "esta declarado que da?".
    Uma funcionalidade critica pedida a um provedor que nao a declara e'
    **recusada**, nao adaptada em silencio.
    """

    candles_historicos: bool = False
    # entregar cotacao e entregar cotacao EM TEMPO REAL sao coisas diferentes:
    # um provedor com atraso declarado faz a primeira e nao faz a segunda
    cotacao: bool = False
    cotacao_em_tempo_real: bool = False
    ticks_em_tempo_real: bool = False
    livro_de_ofertas: bool = False
    intradiario_1m: bool = False
    # timeframes que o provedor declara suportar; vazio = nao declarado
    timeframes: tuple[str, ...] = ()
    # atraso tipico declarado pelo provedor, em segundos. None = desconhecido,
    # que NAO e' o mesmo que zero
    atraso_tipico_s: Optional[float] = None

    @property
    def serve_para_day_trade(self) -> bool:
        """Da para basear entrada intradiaria neste provedor?

        Exige cotacao em tempo real, 1m **e** atraso declarado pequeno. Atraso
        desconhecido nao passa: nao saber o atraso e' motivo para nao usar.
        """
        if not (self.cotacao_em_tempo_real and self.intradiario_1m):
            return False
        return self.atraso_tipico_s is not None and self.atraso_tipico_s <= 60

    def suporta(self, timeframe: str) -> Optional[bool]:
        """``None`` quando o provedor nao declarou seus timeframes."""
        if not self.timeframes:
            return None
        return timeframe in self.timeframes

    def falta_para(self, **exigencias: bool) -> tuple[str, ...]:
        """O que falta para atender as exigencias pedidas."""
        faltando = []
        for nome, exigido in exigencias.items():
            if exigido and not getattr(self, nome, False):
                faltando.append(nome)
        return tuple(faltando)

    def com(self, **campos) -> "Capacidades":
        return replace(self, **campos)

    def para_dict(self) -> dict:
        return {
            "candles_historicos": self.candles_historicos,
            "cotacao": self.cotacao,
            "cotacao_em_tempo_real": self.cotacao_em_tempo_real,
            "ticks_em_tempo_real": self.ticks_em_tempo_real,
            "livro_de_ofertas": self.livro_de_ofertas,
            "intradiario_1m": self.intradiario_1m,
            "timeframes": list(self.timeframes),
            "atraso_tipico_s": self.atraso_tipico_s,
            "serve_para_day_trade": self.serve_para_day_trade,
        }


class CapacidadeAusenteError(RuntimeError):
    """Pediram a um provedor algo que ele nao declara saber fazer."""


def exigir(capacidades: Capacidades, provedor: str, **exigencias: bool) -> None:
    """Barreira explicita. Levanta quando falta capacidade declarada."""
    faltando = capacidades.falta_para(**exigencias)
    if faltando:
        raise CapacidadeAusenteError(
            f"o provedor '{provedor}' nao declara {', '.join(faltando)} - "
            "adaptar um provedor inadequado em silencio e' pior que falhar aqui")
