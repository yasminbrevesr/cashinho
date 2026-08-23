"""Registro automatico: o diario acompanha o Paper Broker sozinho.

``BrokerComDiario`` embrulha qualquer ``Broker`` e implementa a mesma
interface. Toda vez que a corretora encerra uma operacao, o registro entra no
diario - sem ninguem precisar lembrar de anotar.

O que a corretora sabe (precos, quantidade, horarios, resultado) vem dela. O
resto - setup, score, camadas, avisos do auditor - precisa ser informado
ANTES da entrada, com :meth:`anotar_contexto`. Sem contexto, o registro entra
mesmo assim, so que sem a metade que explica o porque: melhor um diario
incompleto do que um trade perdido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...models import Direction
from ..auditor.modelos import AuditResult
from ..broker.base import Broker
from ..broker.modelos import Balance, Operacao, Order, Position
from ..oportunidade.modelos import Opportunity
from .diario import DiarioDeTrades
from .modelos import MOTIVOS_DE_SAIDA, Registro


@dataclass
class ContextoDeEntrada:
    """O que a analise dizia quando a posicao foi aberta.

    Guarda os FATOS derivados, nao os objetos: assim o contexto sobrevive a
    um encerramento do processo, que e' o caso normal de quem opera por
    varias chamadas de linha de comando.
    """

    stop: float = 0.0
    alvo: float = 0.0
    setup: str = ""
    score: float = 0.0
    timeframe_context: str = ""
    timeframe_trend: str = ""
    timeframe_setup: str = ""
    timeframe_trigger: str = ""
    motivo_entrada: tuple[str, ...] = ()
    condicoes_de_mercado: tuple[str, ...] = ()
    warnings_auditor: tuple[str, ...] = ()
    observacao: str = ""

    @classmethod
    def de_oportunidade(
        cls,
        oportunidade: Optional[Opportunity] = None,
        auditoria: Optional[AuditResult] = None,
        motivo_entrada: tuple[str, ...] = (),
        observacao: str = "",
        stop: float = 0.0,
        alvo: float = 0.0,
        setup: str = "",
    ) -> "ContextoDeEntrada":
        op = oportunidade
        condicoes: tuple[str, ...] = ()
        if op is not None and op.leitura is not None:
            condicoes = tuple(
                f"{c.timeframe} {c.papel}: {c.valor}" for c in op.leitura.camadas
            )
        return cls(
            stop=op.stop if op else stop,
            alvo=op.target if op else alvo,
            setup=op.setup if op else setup,
            score=(auditoria.score_final if auditoria else (op.score if op else 0.0)),
            timeframe_context=op.timeframe_context if op else "",
            timeframe_trend=op.timeframe_trend if op else "",
            timeframe_setup=op.timeframe_setup if op else "",
            timeframe_trigger=op.timeframe_trigger if op else "",
            motivo_entrada=motivo_entrada or (tuple(op.reasons[:4]) if op else ()),
            condicoes_de_mercado=condicoes,
            warnings_auditor=(auditoria.warnings if auditoria else ()),
            observacao=observacao,
        )

    def para_dict(self) -> dict:
        return {
            "stop": self.stop, "alvo": self.alvo, "setup": self.setup, "score": self.score,
            "timeframe_context": self.timeframe_context,
            "timeframe_trend": self.timeframe_trend,
            "timeframe_setup": self.timeframe_setup,
            "timeframe_trigger": self.timeframe_trigger,
            "motivo_entrada": list(self.motivo_entrada),
            "condicoes_de_mercado": list(self.condicoes_de_mercado),
            "warnings_auditor": list(self.warnings_auditor),
            "observacao": self.observacao,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "ContextoDeEntrada":
        return cls(
            stop=float(dados.get("stop", 0.0)), alvo=float(dados.get("alvo", 0.0)),
            setup=dados.get("setup", ""), score=float(dados.get("score", 0.0)),
            timeframe_context=dados.get("timeframe_context", ""),
            timeframe_trend=dados.get("timeframe_trend", ""),
            timeframe_setup=dados.get("timeframe_setup", ""),
            timeframe_trigger=dados.get("timeframe_trigger", ""),
            motivo_entrada=tuple(dados.get("motivo_entrada", ())),
            condicoes_de_mercado=tuple(dados.get("condicoes_de_mercado", ())),
            warnings_auditor=tuple(dados.get("warnings_auditor", ())),
            observacao=dados.get("observacao", ""),
        )


class BrokerComDiario(Broker):
    """Corretora que anota sozinha o que encerrou."""

    def __init__(self, broker: Broker, diario: Optional[DiarioDeTrades] = None,
                 arquivo: Optional[Path] = None):
        self.broker = broker
        # `diario or DiarioDeTrades()` seria uma armadilha: DiarioDeTrades
        # define __len__, entao um diario VAZIO e' falsy e seria trocado por
        # outro em silencio - os registros iriam para um objeto que ninguem ve
        self.diario = diario if diario is not None else DiarioDeTrades()
        self.arquivo = Path(arquivo) if arquivo else None
        self._contextos: dict[str, ContextoDeEntrada] = {}
        self._registradas: int = len(self.diario)

    @property
    def nome(self) -> str:  # type: ignore[override]
        return f"{self.broker.nome}+diario"

    @property
    def simulado(self) -> bool:  # type: ignore[override]
        return self.broker.simulado

    # ------------------------------------------------------------------
    def anotar_contexto(
        self,
        symbol: str,
        oportunidade: Optional[Opportunity] = None,
        auditoria: Optional[AuditResult] = None,
        motivo_entrada: tuple[str, ...] = (),
        observacao: str = "",
        stop: float = 0.0,
        alvo: float = 0.0,
        setup: str = "",
    ) -> ContextoDeEntrada:
        """Guarda o porque da entrada, para o diario ter as duas metades."""
        contexto = ContextoDeEntrada.de_oportunidade(
            oportunidade, auditoria, motivo_entrada, observacao, stop, alvo, setup
        )
        self._contextos[symbol.upper()] = contexto
        return contexto

    def contexto(self, symbol: str) -> Optional[ContextoDeEntrada]:
        return self._contextos.get(symbol.upper())

    # ------------------------------------------------------------------
    # interface Broker - tudo delega e depois sincroniza
    # ------------------------------------------------------------------
    def place_order(self, order: Order) -> Order:
        enviada = self.broker.place_order(order)
        self.sincronizar()
        return enviada

    def place_oco(self, stop_loss: Order, take_profit: Order):
        if not hasattr(self.broker, "place_oco"):
            raise NotImplementedError(f"{self.broker.nome} nao simula OCO")
        par = self.broker.place_oco(stop_loss, take_profit)
        self.sincronizar()
        return par

    def cancel_order(self, order_id: str) -> Order:
        return self.broker.cancel_order(order_id)

    def get_orders(self, symbol: Optional[str] = None, abertas: bool = False) -> list[Order]:
        return self.broker.get_orders(symbol, abertas)

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        return self.broker.get_positions(symbol)

    def get_balance(self) -> Balance:
        return self.broker.get_balance()

    def get_trades(self) -> list[Operacao]:
        return self.broker.get_trades()

    def processar(self, symbol: str, candle) -> list[Order]:
        executadas = self.broker.processar(symbol, candle)
        self.sincronizar()
        return executadas

    def acionar_kill_switch(self, motivo: str = "acionado manualmente"):
        if hasattr(self.broker, "acionar_kill_switch"):
            return self.broker.acionar_kill_switch(motivo)
        return self.cancel_all()

    def liberar_kill_switch(self) -> None:
        if hasattr(self.broker, "liberar_kill_switch"):
            self.broker.liberar_kill_switch()

    # ------------------------------------------------------------------
    def contextos_para_dict(self) -> dict:
        """Os contextos por ativo - precisam sobreviver entre chamadas."""
        return {ativo: c.para_dict() for ativo, c in self._contextos.items()}

    def carregar_contextos(self, dados: dict) -> None:
        for ativo, d in (dados or {}).items():
            self._contextos[ativo.upper()] = ContextoDeEntrada.de_dict(d)

    def sincronizar(self) -> list[Registro]:
        """Transforma em registro toda operacao encerrada que ainda nao entrou."""
        operacoes = self.broker.get_trades()
        novas = operacoes[self._registradas:]
        self._registradas = len(operacoes)

        registros = []
        for operacao in novas:
            registro = self._registro(operacao)
            self.diario.registrar(registro)
            if self.arquivo is not None:
                self.diario.anexar(self.arquivo, registro)
            registros.append(registro)
        return registros

    def _registro(self, operacao: Operacao) -> Registro:
        contexto = self._contextos.get(operacao.symbol.upper()) or ContextoDeEntrada()
        return Registro(
            symbol=operacao.symbol,
            direcao=operacao.direcao,
            aberta_em=operacao.aberta_em,
            fechada_em=operacao.fechada_em,
            quantidade=operacao.quantidade,
            entrada=operacao.preco_entrada,
            saida=operacao.preco_saida,
            custos=operacao.custos,
            resultado=operacao.resultado,
            stop=contexto.stop,
            alvo=contexto.alvo,
            setup=contexto.setup,
            score=contexto.score,
            timeframe_context=contexto.timeframe_context,
            timeframe_trend=contexto.timeframe_trend,
            timeframe_setup=contexto.timeframe_setup,
            timeframe_trigger=contexto.timeframe_trigger,
            motivo_entrada=contexto.motivo_entrada,
            motivo_saida=MOTIVOS_DE_SAIDA.get(operacao.motivo, operacao.motivo or "encerrada"),
            condicoes_de_mercado=contexto.condicoes_de_mercado,
            warnings_auditor=contexto.warnings_auditor,
            observacao=contexto.observacao,
        )
