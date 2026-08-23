"""Os tres estados de um componente - e como eles se combinam."""

from __future__ import annotations

from enum import Enum


class EstadoDeSaude(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"

    @property
    def peso(self) -> int:
        return {"ONLINE": 0, "DEGRADED": 1, "OFFLINE": 2}[self.value]

    @property
    def rotulo(self) -> str:
        return self.value

    @property
    def saudavel(self) -> bool:
        return self is EstadoDeSaude.ONLINE

    @property
    def descricao(self) -> str:
        return {
            "ONLINE": "funcionando",
            "DEGRADED": "funcionando com ressalva",
            "OFFLINE": "fora do ar",
        }[self.value]


def pior_de(estados) -> EstadoDeSaude:
    """O pior estado do conjunto - vazio conta como OFFLINE.

    Um painel que mostra ONLINE porque a media deu bom seria pior que painel
    nenhum: o que interessa e' o pedaco quebrado, nao o conjunto.
    """
    lista = list(estados)
    if not lista:
        return EstadoDeSaude.OFFLINE
    return max(lista, key=lambda e: e.peso)


class Modo(str, Enum):
    """Em que modo o robo esta rodando agora."""

    ANALISE = "ANALISE"          # so analisa, nao envia ordem
    PAPER = "PAPER TRADING"      # ordens simuladas
    REPLAY = "REPLAY"            # reproducao de pregao passado
    BACKTEST = "BACKTEST"
    REAL = "REAL"                # nao implementado nesta versao

    @property
    def envia_ordem_de_verdade(self) -> bool:
        return self is Modo.REAL

    @property
    def descricao(self) -> str:
        return {
            "ANALISE": "so analisa e sugere - nenhuma ordem e' enviada",
            "PAPER TRADING": "ordens simuladas no Paper Broker",
            "REPLAY": "reproduzindo um pregao passado",
            "BACKTEST": "rodando sobre historico",
            "REAL": "ordens de verdade - nao implementado nesta versao",
        }[self.value]
