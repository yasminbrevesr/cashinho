"""As sondas: uma por componente do painel.

Cada sonda le o que **ja foi observado** (telemetria) ou o estado real do
objeto (broker, risco, agenda) e devolve um :class:`Componente`. Nenhuma sonda
inventa numero: componente sem noticia aparece como OFFLINE com o motivo
"nunca reportou", que e' informacao verdadeira sobre o sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Sequence

from ...models import BRT, formata_dinheiro
from ..mtf.session import Sessao
from .estados import EstadoDeSaude
from .modelos import NOMES, Componente
from .telemetria import Telemetria


@dataclass(frozen=True)
class LimiaresSaude:
    """Quando um componente passa de ONLINE para DEGRADED e para OFFLINE."""

    # dados de mercado: atraso tolerado antes de virar degradado / fora do ar
    market_data_degradado_min: float = 3.0
    market_data_offline_min: float = 15.0
    # demais componentes: quanto tempo sem reportar ate soar o alarme
    silencio_degradado_min: float = 30.0
    silencio_offline_min: float = 120.0
    latencia_degradada_ms: float = 2_000.0
    latencia_offline_ms: float = 10_000.0
    erros_para_degradar: int = 1
    erros_para_derrubar: int = 5
    janela_de_erros_min: float = 30.0

    def para_dict(self) -> dict:
        return {
            "market_data_degradado_min": self.market_data_degradado_min,
            "market_data_offline_min": self.market_data_offline_min,
            "silencio_degradado_min": self.silencio_degradado_min,
            "silencio_offline_min": self.silencio_offline_min,
            "latencia_degradada_ms": self.latencia_degradada_ms,
            "latencia_offline_ms": self.latencia_offline_ms,
            "erros_para_degradar": self.erros_para_degradar,
            "erros_para_derrubar": self.erros_para_derrubar,
            "janela_de_erros_min": self.janela_de_erros_min,
        }


class Sonda(ABC):
    """Contrato de uma sonda."""

    chave: str = ""
    critico: bool = False

    def __init__(self, telemetria: Optional[Telemetria] = None,
                 limiares: Optional[LimiaresSaude] = None):
        self.telemetria = telemetria or Telemetria()
        self.limiares = limiares or LimiaresSaude()

    @property
    def nome(self) -> str:
        return NOMES.get(self.chave, self.chave)

    @abstractmethod
    def verificar(self, instante: datetime) -> Componente:
        """Devolve a saude do componente neste instante."""

    # -- utilitarios para as implementacoes ------------------------------
    def _erros(self, instante: datetime) -> tuple:
        return tuple(self.telemetria.erros_recentes(
            self.chave, self.limiares.janela_de_erros_min, instante))

    def _por_erros(self, erros) -> Optional[EstadoDeSaude]:
        lim = self.limiares
        if len(erros) >= lim.erros_para_derrubar:
            return EstadoDeSaude.OFFLINE
        if len(erros) >= lim.erros_para_degradar:
            return EstadoDeSaude.DEGRADED
        return None

    def _por_latencia(self, latencia: Optional[float]) -> Optional[EstadoDeSaude]:
        if latencia is None:
            return None
        if latencia >= self.limiares.latencia_offline_ms:
            return EstadoDeSaude.OFFLINE
        if latencia >= self.limiares.latencia_degradada_ms:
            return EstadoDeSaude.DEGRADED
        return None

    def _componente(self, estado: EstadoDeSaude, detalhe: str, instante: datetime,
                    ultimo: Optional[datetime] = None, modo: str = "") -> Componente:
        return Componente(
            chave=self.chave, nome=self.nome, estado=estado, detalhe=detalhe,
            ultimo_timestamp=ultimo,
            latencia_ms=self.telemetria.latencia_ms(self.chave),
            erros=self._erros(instante), modo=modo, critico=self.critico,
        )


def _pior(*estados) -> EstadoDeSaude:
    conhecidos = [e for e in estados if e is not None]
    return max(conhecidos, key=lambda e: e.peso) if conhecidos else EstadoDeSaude.ONLINE


# ---------------------------------------------------------------------------
# Market Data - o unico componente critico
# ---------------------------------------------------------------------------


class SondaMarketData(Sonda):
    """Dado de mercado: fresco, atrasado ou fora do ar.

    Para este componente, **atraso alem do tolerado nao e' ressalva, e' queda**:
    operar com candle velho e' pior do que nao operar. Por isso o estado vai
    direto para OFFLINE - e OFFLINE bloqueia operacao nova.

    Fora do pregao o relogio nao conta: as 20h de uma sexta o ultimo candle e'
    das 17h55 e isso e' o certo, nao uma falha.
    """

    chave = "market_data"
    critico = True

    def __init__(self, telemetria=None, limiares=None,
                 ultimo_dado: Optional[Callable[[], Optional[datetime]]] = None,
                 sessao: Optional[Sessao] = None, servico=None):
        super().__init__(telemetria, limiares)
        self._ultimo_dado = ultimo_dado
        self.sessao = sessao or Sessao()
        # o MarketDataService, quando configurado: e' dele que sai qual
        # provedor serve cada papel e se ha analise de tempo real
        self.servico = servico

    def verificar(self, instante: datetime) -> Componente:
        ultimo = (self._ultimo_dado() if self._ultimo_dado
                  else self.telemetria.ultimo_dado(self.chave))
        erros = self._erros(instante)

        if ultimo is None:
            return self._componente(
                EstadoDeSaude.OFFLINE,
                "nenhum dado recebido ate agora - o robo nao esta vendo o mercado",
                instante)

        atraso = self._atraso_util(ultimo, instante)
        lim = self.limiares
        if atraso >= lim.market_data_offline_min:
            estado = EstadoDeSaude.OFFLINE
            detalhe = (f"ultimo dado ha {atraso:.0f} min, acima do limite de "
                       f"{lim.market_data_offline_min:.0f} min: dado velho nao serve "
                       "para decidir")
        elif atraso >= lim.market_data_degradado_min:
            estado = EstadoDeSaude.DEGRADED
            detalhe = f"ultimo dado ha {atraso:.0f} min"
        else:
            estado = EstadoDeSaude.ONLINE
            detalhe = (f"dado de {ultimo:%H:%M}" if self.sessao.contem(instante)
                       else f"fora do pregao - ultimo dado de {ultimo:%d/%m %H:%M}")

        estado = _pior(estado, self._por_erros(erros),
                       self._por_latencia(self.telemetria.latencia_ms(self.chave)))
        return self._componente(estado, detalhe, instante, ultimo,
                                modo=self._modo_dos_provedores())

    def _modo_dos_provedores(self) -> str:
        """Quem serve histórico, quem serve tempo real - ou a falta."""
        if self.servico is None:
            return ""
        dados = self.servico.para_dict()
        historico = (dados["historico"] or {}).get("nome", "nao configurado")
        tempo_real = (dados["tempo_real"] or {}).get("nome", "NAO CONFIGURADO")
        return f"historico {historico} · tempo real {tempo_real}"

    def _atraso_util(self, ultimo: datetime, instante: datetime) -> float:
        """Minutos de atraso, sem contar o tempo de mercado fechado.

        Dentro do pregao e' o relogio de parede. Fora dele, o atraso e' medido
        ate o fechamento da **ultima sessao** - as 20h de sexta um candle das
        17h55 esta em dia, mas um candle de tres semanas atras nao fica em dia
        so porque hoje e' domingo.
        """
        if self.sessao.contem(instante):
            return max(0.0, (instante - ultimo).total_seconds() / 60)
        fim = self._fim_da_ultima_sessao(instante)
        if fim is None:  # nenhum pregao encontrado para tras: nao da para medir
            return max(0.0, (instante - ultimo).total_seconds() / 60)
        return max(0.0, (fim - ultimo).total_seconds() / 60)

    def _fim_da_ultima_sessao(self, instante: datetime,
                              limite_dias: int = 10) -> Optional[datetime]:
        """O fechamento do pregao mais recente que ja terminou."""
        dia = instante.astimezone(BRT).date()
        for _ in range(limite_dias):
            if self.sessao.eh_dia_util(dia):
                _, fim = self.sessao.limites(dia)
                if fim <= instante:
                    return fim
            dia -= timedelta(days=1)
        return None


# ---------------------------------------------------------------------------
# componentes que reportam pela telemetria
# ---------------------------------------------------------------------------


class SondaPorTelemetria(Sonda):
    """Sonda generica: quem trabalha anota, a sonda le.

    Silencio nao vira ONLINE. Um componente que nunca reportou aparece OFFLINE
    dizendo isso - o painel existe para mostrar o que nao esta funcionando, e
    "nunca deu sinal" e' uma das formas de nao funcionar.
    """

    def __init__(self, chave: str, telemetria=None, limiares=None,
                 opcional: bool = False, modo: str = "", nome: str = ""):
        super().__init__(telemetria, limiares)
        self.chave = chave
        self.opcional = opcional
        self._modo = modo
        self._nome = nome

    @property
    def nome(self) -> str:
        return self._nome or NOMES.get(self.chave, self.chave)

    def verificar(self, instante: datetime) -> Componente:
        erros = self._erros(instante)
        ultimo_ok = self.telemetria.ultimo_ok(self.chave)
        ultimo_dado = self.telemetria.ultimo_dado(self.chave)
        detalhe = self.telemetria.anotacoes(self.chave).detalhe

        if ultimo_ok is None:
            if self.opcional and not erros:
                return self._componente(
                    EstadoDeSaude.DEGRADED, "nunca usado nesta sessao", instante,
                    modo=self._modo)
            return self._componente(
                EstadoDeSaude.OFFLINE, "nunca reportou atividade", instante,
                modo=self._modo)

        silencio = (instante - ultimo_ok).total_seconds() / 60
        lim = self.limiares
        if silencio >= lim.silencio_offline_min:
            estado = EstadoDeSaude.OFFLINE
            detalhe = detalhe or f"sem atividade ha {silencio:.0f} min"
        elif silencio >= lim.silencio_degradado_min:
            estado = EstadoDeSaude.DEGRADED
            detalhe = detalhe or f"sem atividade ha {silencio:.0f} min"
        else:
            estado = EstadoDeSaude.ONLINE
            detalhe = detalhe or f"ultima atividade {ultimo_ok:%H:%M}"

        estado = _pior(estado, self._por_erros(erros),
                       self._por_latencia(self.telemetria.latencia_ms(self.chave)))
        return self._componente(estado, detalhe, instante,
                                ultimo_dado or ultimo_ok, self._modo)


# ---------------------------------------------------------------------------
# componentes que sabem responder por si
# ---------------------------------------------------------------------------


class SondaBanco(Sonda):
    """Database: o diario em JSONL - existe, da para escrever, e ate quando foi."""

    chave = "database"

    def __init__(self, caminho, telemetria=None, limiares=None):
        super().__init__(telemetria, limiares)
        self.caminho = Path(caminho)

    def verificar(self, instante: datetime) -> Componente:
        erros = self._erros(instante)
        pasta = self.caminho.parent if self.caminho.suffix else self.caminho

        if not pasta.exists():
            return self._componente(
                EstadoDeSaude.OFFLINE,
                f"pasta inexistente: {pasta} - nada seria gravado", instante)

        import os

        if not os.access(pasta, os.W_OK):
            return self._componente(
                EstadoDeSaude.OFFLINE,
                f"sem permissao de escrita em {pasta}: operacoes nao seriam registradas",
                instante)

        if not self.caminho.exists():
            estado = _pior(EstadoDeSaude.DEGRADED, self._por_erros(erros))
            return self._componente(
                estado, f"{self.caminho.name} ainda nao existe (nenhum registro gravado)",
                instante)

        from datetime import timezone

        modificado = datetime.fromtimestamp(self.caminho.stat().st_mtime,
                                            tz=instante.tzinfo or timezone.utc)
        linhas = sum(1 for _ in self.caminho.open(encoding="utf-8"))
        estado = _pior(EstadoDeSaude.ONLINE, self._por_erros(erros))
        return self._componente(
            estado, f"{linhas} registro(s) · ultima gravacao {modificado:%d/%m %H:%M}",
            instante, modificado)


class SondaBroker(Sonda):
    """Paper Broker: esta ligado, em que modo, com quanto e com o que aberto."""

    chave = "paper_broker"

    def __init__(self, broker=None, telemetria=None, limiares=None):
        super().__init__(telemetria, limiares)
        self.broker = broker

    def verificar(self, instante: datetime) -> Componente:
        erros = self._erros(instante)
        if self.broker is None:
            return self._componente(EstadoDeSaude.OFFLINE, "nenhum broker conectado",
                                    instante)
        try:
            saldo = self.broker.get_balance()
            abertas = self.broker.get_orders(abertas=True)
            posicoes = self.broker.get_positions()
        except Exception as e:  # a sonda nunca derruba o painel
            self.telemetria.erro(self.chave, f"falha ao consultar o broker: {e}")
            return self._componente(EstadoDeSaude.OFFLINE,
                                    f"falha ao consultar o broker: {e}", instante)

        modo = "simulado" if getattr(self.broker, "simulado", True) else "REAL"
        detalhe = (f"patrimonio {formata_dinheiro(saldo.patrimonio)} · {len(abertas)} "
                   f"ordem(ns) aberta(s) · {len(posicoes)} posicao(oes)")
        estado = _pior(EstadoDeSaude.ONLINE, self._por_erros(erros))
        return self._componente(estado, detalhe, instante, modo=modo)


class SondaRisco(Sonda):
    """Risk Manager: liberado ou bloqueado, e por que."""

    chave = "risk_manager"

    def __init__(self, risco=None, telemetria=None, limiares=None):
        super().__init__(telemetria, limiares)
        self.risco = risco

    def verificar(self, instante: datetime) -> Componente:
        erros = self._erros(instante)
        if self.risco is None:
            return self._componente(EstadoDeSaude.OFFLINE,
                                    "nenhum Risk Manager conectado", instante)
        status = self.risco.status()
        if status.kill_switch is not None:
            return self._componente(
                EstadoDeSaude.OFFLINE,
                f"KILL SWITCH: {status.kill_switch.motivo}", instante,
                modo=status.rotulo)
        if not status.liberado:
            motivo = "; ".join(status.motivos) or "limite atingido"
            return self._componente(EstadoDeSaude.DEGRADED, motivo, instante,
                                    modo=status.rotulo)
        estado = _pior(EstadoDeSaude.ONLINE, self._por_erros(erros))
        return self._componente(
            estado,
            f"{status.trades_dia} trade(s) hoje · P&L {status.pnl_dia:+.2f} · "
            f"exposicao {status.exposicao_pct:.1f}%",
            instante, modo=status.rotulo)


class SondaNoticias(Sonda):
    """News: a agenda esta disponivel e fresca?"""

    chave = "news"

    def __init__(self, avaliador=None, telemetria=None, limiares=None):
        super().__init__(telemetria, limiares)
        self.avaliador = avaliador

    def verificar(self, instante: datetime) -> Componente:
        erros = self._erros(instante)
        if self.avaliador is None:
            return self._componente(
                EstadoDeSaude.OFFLINE,
                "NOTICIAS INDISPONIVEIS - nenhuma agenda configurada", instante)
        try:
            agenda = self.avaliador.agenda(instante)
        except Exception as e:
            self.telemetria.erro(self.chave, str(e))
            return self._componente(EstadoDeSaude.OFFLINE,
                                    f"falha ao carregar a agenda: {e}", instante)

        if not agenda.confiavel:
            detalhe = agenda.motivo or agenda.disponibilidade.detalhe
            return self._componente(EstadoDeSaude.DEGRADED,
                                    f"{agenda.rotulo} - {detalhe}", instante,
                                    agenda.atualizado_em)
        estado = _pior(EstadoDeSaude.ONLINE, self._por_erros(erros))
        return self._componente(
            estado, f"{len(agenda)} evento(s) na agenda · fonte {agenda.fonte}",
            instante, agenda.atualizado_em)
