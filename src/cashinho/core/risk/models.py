"""Modelos do Risk Manager.

``RiskDecision`` e' congelada de proposito: a decisao do risco e' final. Nao
existe metodo para aprovar uma rejeicao, nem atributo mutavel - uma estrategia
que tente ``decisao.allowed = True`` recebe ``FrozenInstanceError``, e uma
decisao forjada por fora nao passa por :meth:`RiskManager.abrir`, porque o
gerente so aceita decisoes que ele mesmo emitiu e aprovou.

Os campos ``allowed``, ``reason``, ``position_size``, ``monetary_risk`` e
``portfolio_exposure`` mantem o nome em ingles porque sao o contrato publico
do modulo; o resto do projeto segue em portugues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class MotivoRejeicao(str, Enum):
    """Codigos estaveis de rejeicao - para log, metrica e teste."""

    KILL_SWITCH = "kill_switch"
    ORDEM_INVALIDA = "ordem_invalida"
    PERDA_DIARIA = "perda_maxima_diaria"
    DRAWDOWN = "drawdown_maximo"
    PERDAS_CONSECUTIVAS = "perdas_consecutivas"
    MAX_TRADES = "maximo_de_trades"
    POSICAO_EXISTENTE = "posicao_ja_aberta"
    CAPITAL_INSUFICIENTE = "capital_insuficiente"
    EXPOSICAO_ATIVO = "exposicao_maxima_por_ativo"
    EXPOSICAO_TOTAL = "exposicao_maxima_total"
    RISCO_INSUFICIENTE = "risco_insuficiente_para_1_lote"


class Limitador(str, Enum):
    """O que definiu o tamanho final da posicao."""

    RISCO = "risco por operacao"
    CAPITAL = "capital disponivel"
    EXPOSICAO_ATIVO = "exposicao maxima por ativo"
    EXPOSICAO_TOTAL = "exposicao maxima total"
    RISCO_DIARIO = "risco restante do dia"


@dataclass(frozen=True)
class Rejeicao:
    codigo: MotivoRejeicao
    mensagem: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return f"{self.codigo.value}: {self.mensagem}"


@dataclass(frozen=True)
class PedidoOperacao:
    """O que uma estrategia manda para o risco avaliar.

    Repare no que NAO tem aqui: setup, indicador, score, timeframe. O risco
    nao precisa (nem pode) saber de onde veio a ideia.
    """

    symbol: str
    direcao: Direction
    entrada: float
    stop: float
    alvo: Optional[float] = None
    preco_atual: Optional[float] = None
    referencia: str = ""  # identificacao livre da estrategia, so para log

    @property
    def risco_por_acao(self) -> float:
        return abs(self.entrada - self.stop)

    @property
    def stop_coerente(self) -> bool:
        """Compra tem stop abaixo da entrada; venda, acima."""
        if self.direcao is Direction.LONG:
            return self.stop < self.entrada
        return self.stop > self.entrada


@dataclass(frozen=True)
class RiskDecision:
    """Resposta do Risk Manager. Imutavel: rejeicao nao se desfaz."""

    allowed: bool
    reason: str
    position_size: int
    monetary_risk: float
    portfolio_exposure: float

    # detalhamento (opcional para quem so quer os cinco campos acima)
    symbol: str = ""
    direcao: Optional[Direction] = None
    entrada: float = 0.0
    stop: float = 0.0
    risco_por_acao: float = 0.0
    risco_alvo: float = 0.0
    exposicao_da_ordem: float = 0.0
    exposicao_pct: float = 0.0
    limitador: Optional[Limitador] = None
    rejeicoes: tuple[Rejeicao, ...] = ()
    avaliado_em: Optional[datetime] = None
    id: str = ""

    @property
    def rejeitada(self) -> bool:
        return not self.allowed

    @property
    def codigos(self) -> tuple[str, ...]:
        return tuple(r.codigo.value for r in self.rejeicoes)

    def para_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "position_size": self.position_size,
            "monetary_risk": round(self.monetary_risk, 2),
            "portfolio_exposure": round(self.portfolio_exposure, 2),
            "symbol": self.symbol,
            "direcao": self.direcao.value if self.direcao else None,
            "entrada": round(self.entrada, 4),
            "stop": round(self.stop, 4),
            "risco_por_acao": round(self.risco_por_acao, 4),
            "exposicao_pct": round(self.exposicao_pct, 2),
            "limitador": self.limitador.value if self.limitador else None,
            "rejeicoes": [{"codigo": r.codigo.value, "mensagem": r.mensagem} for r in self.rejeicoes],
        }


class RiskRejectionError(RuntimeError):
    """Tentativa de executar uma operacao que o risco nao aprovou."""


@dataclass(frozen=True)
class Position:
    symbol: str
    direcao: Direction
    quantidade: int
    preco_medio: float
    stop: float
    aberta_em: datetime
    decisao_id: str = ""

    @property
    def exposicao(self) -> float:
        return self.quantidade * self.preco_medio

    @property
    def risco_aberto(self) -> float:
        return abs(self.preco_medio - self.stop) * self.quantidade


@dataclass(frozen=True)
class TradeResult:
    symbol: str
    direcao: Direction
    quantidade: int
    preco_entrada: float
    preco_saida: float
    custos: float
    aberto_em: datetime
    fechado_em: datetime

    @property
    def resultado_bruto(self) -> float:
        sinal = 1 if self.direcao is Direction.LONG else -1
        return (self.preco_saida - self.preco_entrada) * self.quantidade * sinal

    @property
    def resultado(self) -> float:
        """Resultado liquido de custos."""
        return self.resultado_bruto - self.custos

    @property
    def perdeu(self) -> bool:
        return self.resultado < 0


@dataclass
class LimiteUso:
    """Quanto de um limite ja foi consumido - alimenta a pagina de risco."""

    nome: str
    usado: float
    limite: float
    unidade: str = "R$"

    @property
    def pct(self) -> float:
        return (self.usado / self.limite * 100.0) if self.limite else 0.0

    @property
    def estourado(self) -> bool:
        return self.usado >= self.limite


@dataclass
class RiskStatus:
    """Fotografia do risco - o que a pagina Risk Manager mostra."""

    liberado: bool
    motivos: list[str]
    capital: float
    patrimonio: float
    capital_pregao: float
    pnl_dia: float
    trades_dia: int
    perdas_consecutivas: int
    drawdown: float
    drawdown_pct: float
    exposicao_total: float
    exposicao_pct: float
    posicoes: list[Position]
    limites: list[LimiteUso]
    kill_switch: Optional["KillSwitch"] = None
    pregao: Optional[date] = None

    @property
    def rotulo(self) -> str:
        return "TRADING LIBERADO" if self.liberado else "TRADING BLOQUEADO"

    def para_dict(self) -> dict:
        return {
            "liberado": self.liberado,
            "rotulo": self.rotulo,
            "motivos": list(self.motivos),
            "capital": round(self.capital, 2),
            "patrimonio": round(self.patrimonio, 2),
            "capital_pregao": round(self.capital_pregao, 2),
            "pnl_dia": round(self.pnl_dia, 2),
            "trades_dia": self.trades_dia,
            "perdas_consecutivas": self.perdas_consecutivas,
            "drawdown": round(self.drawdown, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "exposicao_total": round(self.exposicao_total, 2),
            "exposicao_pct": round(self.exposicao_pct, 2),
            "kill_switch": None if self.kill_switch is None else self.kill_switch.para_dict(),
            "limites": [
                {"nome": l.nome, "usado": round(l.usado, 2), "limite": round(l.limite, 2),
                 "pct": round(l.pct, 1), "unidade": l.unidade, "estourado": l.estourado}
                for l in self.limites
            ],
            "posicoes": [
                {"symbol": p.symbol, "direcao": p.direcao.value, "quantidade": p.quantidade,
                 "preco_medio": round(p.preco_medio, 4), "exposicao": round(p.exposicao, 2)}
                for p in self.posicoes
            ],
        }


@dataclass(frozen=True)
class KillSwitch:
    """Trava geral. Enquanto estiver ativa, nenhuma operacao passa."""

    codigo: str  # "manual" | "perda_diaria" | "drawdown" | "perdas_consecutivas"
    motivo: str
    acionado_em: datetime
    diario: bool = False  # se desarma sozinho no proximo pregao

    def para_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "motivo": self.motivo,
            "acionado_em": self.acionado_em.isoformat(),
            "diario": self.diario,
        }
