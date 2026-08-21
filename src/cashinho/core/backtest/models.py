"""Resultado de um backtest: trades, curva de capital e metricas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from ...models import Direction


class MotivoSaida(str, Enum):
    STOP = "stop"
    ALVO = "alvo"
    FIM_DO_DIA = "fim do dia"
    SINAL_CONTRARIO = "sinal contrario"
    FIM_DOS_DADOS = "fim dos dados"

    @property
    def descricao(self) -> str:
        return {
            MotivoSaida.STOP: "stop acionado",
            MotivoSaida.ALVO: "alvo atingido",
            MotivoSaida.FIM_DO_DIA: "encerrado no fim do pregao",
            MotivoSaida.SINAL_CONTRARIO: "estrategia inverteu o vies",
            MotivoSaida.FIM_DOS_DADOS: "serie acabou com a posicao aberta",
        }[self]


@dataclass(frozen=True)
class BacktestTrade:
    """Uma operacao completa, do preenchimento a saida."""

    symbol: str
    direcao: Direction
    quantidade: int
    entrada_em: datetime
    entrada_preco: float
    saida_em: datetime
    saida_preco: float
    motivo: MotivoSaida
    custos: float
    stop: float
    alvo: float
    risco_planejado: float  # quantidade x (entrada - stop) na hora da decisao
    setup: str = ""
    confianca: float = 0.0

    @property
    def resultado_bruto(self) -> float:
        sinal = 1 if self.direcao is Direction.LONG else -1
        return (self.saida_preco - self.entrada_preco) * self.quantidade * sinal

    @property
    def resultado(self) -> float:
        """Resultado liquido de custos - o unico numero que conta."""
        return self.resultado_bruto - self.custos

    @property
    def venceu(self) -> bool:
        return self.resultado > 0

    @property
    def perdeu(self) -> bool:
        return self.resultado < 0

    @property
    def financeiro(self) -> float:
        return self.quantidade * self.entrada_preco

    @property
    def retorno_pct(self) -> float:
        return (self.resultado / self.financeiro * 100.0) if self.financeiro else 0.0

    @property
    def resultado_em_r(self) -> float:
        """Resultado em multiplos do risco planejado (R)."""
        return self.resultado / self.risco_planejado if self.risco_planejado else 0.0

    @property
    def duracao(self):
        return self.saida_em - self.entrada_em

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direcao": self.direcao.value,
            "quantidade": self.quantidade,
            "entrada_em": self.entrada_em.isoformat(),
            "entrada_preco": round(self.entrada_preco, 4),
            "saida_em": self.saida_em.isoformat(),
            "saida_preco": round(self.saida_preco, 4),
            "motivo": self.motivo.value,
            "custos": round(self.custos, 2),
            "resultado_bruto": round(self.resultado_bruto, 2),
            "resultado": round(self.resultado, 2),
            "resultado_em_r": round(self.resultado_em_r, 3),
            "retorno_pct": round(self.retorno_pct, 3),
            "setup": self.setup,
        }


@dataclass(frozen=True)
class PontoEquity:
    """Patrimonio no fechamento de um candle, ja marcando a posicao aberta."""

    ts: datetime
    equity: float
    realizado: float
    aberto: float  # resultado nao realizado
    exposicao: float  # financeiro alocado
    posicionado: bool

    @property
    def dia(self) -> date:
        return self.ts.date()


@dataclass
class Metricas:
    """As metricas de desempenho de uma rodada."""

    retorno_total: float = 0.0
    retorno_total_pct: float = 0.0
    n_trades: int = 0
    vencedores: int = 0
    perdedores: int = 0
    empates: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    ganho_medio: float = 0.0
    perda_media: float = 0.0
    payoff: Optional[float] = None
    expectancy: float = 0.0
    expectancy_em_r: float = 0.0
    profit_factor: Optional[float] = None
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    exposicao_tempo_pct: float = 0.0
    exposicao_media_pct: float = 0.0
    melhor_trade: float = 0.0
    pior_trade: float = 0.0
    maior_sequencia_ganhos: int = 0
    maior_sequencia_perdas: int = 0
    custos_totais: float = 0.0
    dias: int = 0

    def para_dict(self) -> dict:
        def _r(v, casas=2):
            return None if v is None else round(v, casas)

        return {
            "retorno_total": _r(self.retorno_total),
            "retorno_total_pct": _r(self.retorno_total_pct),
            "n_trades": self.n_trades,
            "vencedores": self.vencedores,
            "perdedores": self.perdedores,
            "win_rate": _r(self.win_rate, 4),
            "loss_rate": _r(self.loss_rate, 4),
            "payoff": _r(self.payoff, 3),
            "expectancy": _r(self.expectancy),
            "expectancy_em_r": _r(self.expectancy_em_r, 3),
            "profit_factor": _r(self.profit_factor, 3),
            "max_drawdown": _r(self.max_drawdown),
            "max_drawdown_pct": _r(self.max_drawdown_pct),
            "sharpe": _r(self.sharpe, 3),
            "sortino": _r(self.sortino, 3),
            "exposicao_tempo_pct": _r(self.exposicao_tempo_pct),
            "exposicao_media_pct": _r(self.exposicao_media_pct),
            "custos_totais": _r(self.custos_totais),
            "dias": self.dias,
        }


@dataclass
class BacktestResult:
    """Tudo o que a rodada produziu."""

    symbol: str
    timeframe: str
    estrategia: str
    capital_inicial: float
    capital_final: float
    inicio: Optional[datetime]
    fim: Optional[datetime]
    trades: list[BacktestTrade] = field(default_factory=list)
    equity: list[PontoEquity] = field(default_factory=list)
    metricas: Metricas = field(default_factory=Metricas)
    sinais_avaliados: int = 0
    sinais_acionaveis: int = 0
    rejeicoes_do_risco: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    experimental: bool = True

    @property
    def curva(self) -> list[float]:
        return [p.equity for p in self.equity]

    def drawdown_series(self) -> list[float]:
        """Drawdown em % a cada ponto da curva."""
        saida: list[float] = []
        pico = self.capital_inicial
        for p in self.equity:
            pico = max(pico, p.equity)
            saida.append((pico - p.equity) / pico * 100.0 if pico else 0.0)
        return saida

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "estrategia": self.estrategia,
            "capital_inicial": round(self.capital_inicial, 2),
            "capital_final": round(self.capital_final, 2),
            "inicio": self.inicio.isoformat() if self.inicio else None,
            "fim": self.fim.isoformat() if self.fim else None,
            "metricas": self.metricas.para_dict(),
            "trades": [t.para_dict() for t in self.trades],
            "equity": [
                {"ts": p.ts.isoformat(), "equity": round(p.equity, 2), "posicionado": p.posicionado}
                for p in self.equity
            ],
            "sinais_avaliados": self.sinais_avaliados,
            "sinais_acionaveis": self.sinais_acionaveis,
            "rejeicoes_do_risco": dict(self.rejeicoes_do_risco),
            "avisos": list(self.avisos),
            "experimental": self.experimental,
        }
