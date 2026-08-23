"""De onde vem a agenda de eventos.

Nenhuma fonte deste modulo gera evento por conta propria. Um registro so vira
:class:`Evento` se trouxer tipo, data, severidade, confianca e **origem**; o
que nao trouxer e' descartado com o motivo guardado, nunca completado com um
palpite razoavel.

Sobre feeds de noticia em tempo real: nao ha aqui nenhum integrado. Os
provedores confiaveis sao pagos e os gratuitos nao tem compromisso de
atualizacao - e uma agenda de eventos que atrasa e' pior que agenda nenhuma,
porque parece que existe. A fonte suportada nesta versao e' o **arquivo de
calendario** que voce mantem ou exporta da corretora. Ver README:
FONTE DE NOTICIAS EM TEMPO REAL A CONFIRMAR.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ...models import BRT
from .modelos import AgendaDeEventos, Evento, EventoInvalidoError, agenda_indisponivel
from .tipos import Disponibilidade, Severidade, TipoDeEvento, ViesDirecional

VALIDADE_PADRAO_MIN = 12 * 60  # meio dia: um calendario mais velho que isso nao vale


class FonteDeEventos(ABC):
    """Contrato de uma fonte de eventos."""

    nome: str = "fonte"

    @abstractmethod
    def carregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        """Devolve a agenda. Nunca levanta: falha vira agenda indisponivel."""


def evento_de_dict(bruto: dict, fonte_padrao: str = "") -> Evento:
    """Converte um registro em :class:`Evento` - ou explica por que nao da."""
    if not isinstance(bruto, dict):
        raise EventoInvalidoError("registro nao e' um objeto")

    faltando = [c for c in ("event_type", "timestamp", "severity") if not bruto.get(c)]
    if faltando:
        raise EventoInvalidoError(f"faltam campos obrigatorios: {', '.join(faltando)}")

    try:
        tipo = TipoDeEvento(str(bruto["event_type"]).strip().lower())
    except ValueError:
        raise EventoInvalidoError(
            f"tipo de evento desconhecido: {bruto['event_type']!r} "
            f"(conhecidos: {', '.join(t.value for t in TipoDeEvento)})"
        ) from None

    try:
        severidade = Severidade(str(bruto["severity"]).strip().lower())
    except ValueError:
        raise EventoInvalidoError(f"severidade desconhecida: {bruto['severity']!r}") from None

    vies_bruto = str(bruto.get("directional_bias", "indefinido")).strip().lower()
    try:
        vies = ViesDirecional(vies_bruto)
    except ValueError:
        raise EventoInvalidoError(f"vies desconhecido: {vies_bruto!r}") from None

    try:
        ts = _data(bruto["timestamp"])
    except ValueError as e:
        raise EventoInvalidoError(f"timestamp invalido: {bruto['timestamp']!r} ({e})") from None

    confianca = bruto.get("confidence", 1.0)
    try:
        confianca = float(confianca)
    except (TypeError, ValueError):
        raise EventoInvalidoError(f"confidence invalida: {confianca!r}") from None

    fonte = str(bruto.get("source") or fonte_padrao or "").strip()
    return Evento(
        event_type=tipo,
        symbol=str(bruto.get("symbol") or "").strip(),
        timestamp=ts,
        severity=severidade,
        directional_bias=vies,
        confidence=confianca,
        source=fonte,
        titulo=str(bruto.get("titulo") or bruto.get("title") or "").strip(),
        detalhe=str(bruto.get("detalhe") or bruto.get("detail") or "").strip(),
        confirmado=bool(bruto.get("confirmado", bruto.get("confirmed", True))),
    )


def _data(valor) -> datetime:
    if isinstance(valor, datetime):
        ts = valor
    else:
        ts = datetime.fromisoformat(str(valor).strip())
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=BRT)
    return ts


class FonteEmMemoria(FonteDeEventos):
    """Agenda montada no codigo - para testes e para integracao."""

    nome = "memoria"

    def __init__(self, eventos: Sequence[Evento] = (),
                 atualizado_em: Optional[datetime] = None,
                 disponibilidade: Disponibilidade = Disponibilidade.DISPONIVEL):
        self.eventos = tuple(eventos)
        self.atualizado_em = atualizado_em
        self.disponibilidade = disponibilidade

    def carregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        agora = instante or datetime.now(BRT)
        return AgendaDeEventos(
            eventos=self.eventos, disponibilidade=self.disponibilidade,
            atualizado_em=self.atualizado_em or agora, fonte=self.nome,
        )


class FonteArquivo(FonteDeEventos):
    """Calendario em JSON, mantido por voce ou exportado da corretora.

    Formato::

        {
          "atualizado_em": "2026-08-21T09:00:00-03:00",
          "fonte": "calendario manual",
          "eventos": [
            {"event_type": "resultados", "symbol": "PETR4",
             "timestamp": "2026-08-21T18:00:00-03:00", "severity": "alta",
             "directional_bias": "indefinido", "confidence": 0.9,
             "source": "RI da companhia", "titulo": "2T26"}
          ]
        }

    ``atualizado_em`` nao e' enfeite: e' o que separa "nao ha evento" de
    "ninguem atualizou isso desde a semana passada".
    """

    nome = "arquivo"

    def __init__(self, caminho, validade_min: float = VALIDADE_PADRAO_MIN):
        self.caminho = Path(caminho)
        self.validade_min = validade_min

    def carregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        agora = instante or datetime.now(BRT)

        if not self.caminho.exists():
            return agenda_indisponivel(
                f"arquivo de eventos nao encontrado: {self.caminho}", self.nome,
                Disponibilidade.SEM_FONTE)

        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return agenda_indisponivel(f"nao foi possivel ler {self.caminho}: {e}", self.nome)

        if not isinstance(dados, dict) or "eventos" not in dados:
            return agenda_indisponivel(
                f"{self.caminho}: formato inesperado (esperado um objeto com 'eventos')",
                self.nome)

        atualizado = None
        if dados.get("atualizado_em"):
            try:
                atualizado = _data(dados["atualizado_em"])
            except ValueError:
                return agenda_indisponivel(
                    f"{self.caminho}: 'atualizado_em' invalido - sem isso nao da para "
                    "saber se a agenda vale", self.nome)
        if atualizado is None:
            return agenda_indisponivel(
                f"{self.caminho}: sem 'atualizado_em'. Uma agenda sem data de "
                "atualizacao nao pode ser considerada fresca", self.nome)

        eventos: list[Evento] = []
        descartados: list[str] = []
        fonte_padrao = str(dados.get("fonte") or "").strip()
        for i, bruto in enumerate(dados.get("eventos") or []):
            try:
                eventos.append(evento_de_dict(bruto, fonte_padrao))
            except EventoInvalidoError as e:
                descartados.append(f"registro {i}: {e}")

        idade = (agora - atualizado).total_seconds() / 60
        if idade > self.validade_min:
            estado = Disponibilidade.DESATUALIZADA
            motivo = (f"agenda atualizada ha {idade / 60:.1f}h, acima da validade de "
                      f"{self.validade_min / 60:.1f}h")
        else:
            estado, motivo = Disponibilidade.DISPONIVEL, ""

        return AgendaDeEventos(
            eventos=tuple(sorted(eventos, key=lambda e: e.timestamp)),
            disponibilidade=estado,
            atualizado_em=atualizado,
            fonte=fonte_padrao or self.nome,
            motivo=motivo,
            descartados=tuple(descartados),
        )


class FonteComposta(FonteDeEventos):
    """Varias agendas somadas - com o estado do elo mais fraco.

    Se uma das fontes falhou, a agenda combinada tem um buraco que ninguem
    consegue ver de dentro. Por isso o estado nao e' o da melhor fonte: e' o
    da pior.
    """

    nome = "composta"

    _ORDEM = {
        Disponibilidade.DISPONIVEL: 3,
        Disponibilidade.DESATUALIZADA: 2,
        Disponibilidade.INDISPONIVEL: 1,
        Disponibilidade.SEM_FONTE: 0,
    }

    def __init__(self, fontes: Sequence[FonteDeEventos]):
        if not fontes:
            raise ValueError("informe ao menos uma fonte")
        self.fontes = tuple(fontes)

    def carregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        agora = instante or datetime.now(BRT)
        eventos: list[Evento] = []
        descartados: list[str] = []
        motivos: list[str] = []
        pior = Disponibilidade.DISPONIVEL
        atualizacoes: list[datetime] = []

        for f in self.fontes:
            agenda = f.carregar(agora)
            eventos.extend(agenda.eventos)
            descartados.extend(agenda.descartados)
            if agenda.motivo:
                motivos.append(f"{f.nome}: {agenda.motivo}")
            if self._ORDEM[agenda.disponibilidade] < self._ORDEM[pior]:
                pior = agenda.disponibilidade
            if agenda.atualizado_em:
                atualizacoes.append(agenda.atualizado_em)

        return AgendaDeEventos(
            eventos=tuple(sorted(eventos, key=lambda e: e.timestamp)),
            disponibilidade=pior,
            atualizado_em=min(atualizacoes) if atualizacoes else None,
            fonte=", ".join(f.nome for f in self.fontes),
            motivo="; ".join(motivos),
            descartados=tuple(descartados),
        )


class SemFonte(FonteDeEventos):
    """O padrao quando nao ha nada configurado: diz isso, em vez de fingir."""

    nome = "sem fonte"

    def carregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        return agenda_indisponivel(
            "nenhuma fonte de eventos configurada - o robo esta operando as cegas "
            "quanto a agenda", self.nome, Disponibilidade.SEM_FONTE)
