"""Atalhos para montar cenarios de risco nos testes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from cashinho.core.risk import PedidoOperacao, RiskConfig, RiskManager, RiskState
from cashinho.models import BRT, Direction

AGORA = datetime(2026, 8, 20, 11, 0, tzinfo=BRT)


def relogio(momento: datetime = AGORA):
    return lambda: momento


def config(**campos) -> RiskConfig:
    """Config previsivel: sem teto de exposicao atrapalhando os testes de risco."""
    base = dict(
        capital=100_000.0,
        risco_por_trade_pct=1.0,
        exposicao_max_por_ativo_pct=100.0,
        exposicao_max_total_pct=100.0,
        perda_max_diaria_pct=3.0,
        max_trades_dia=5,
        max_perdas_consecutivas=3,
        drawdown_max_pct=10.0,
        permitir_fracionario=True,
    )
    base.update(campos)
    return RiskConfig(**base)


def gerente(cfg: Optional[RiskConfig] = None, **campos) -> RiskManager:
    cfg = cfg or config(**campos)
    return RiskManager(cfg, RiskState(capital_inicial=cfg.capital), relogio())


def compra(entrada: float = 10.0, stop: float = 9.0, symbol: str = "PETR4") -> PedidoOperacao:
    return PedidoOperacao(symbol, Direction.LONG, entrada, stop)


def venda(entrada: float = 10.0, stop: float = 11.0, symbol: str = "PETR4") -> PedidoOperacao:
    return PedidoOperacao(symbol, Direction.SHORT, entrada, stop)


def perder(rm: RiskManager, valor: float, symbol: str = "PETR4") -> None:
    """Abre e fecha uma operacao com prejuizo de ``valor`` reais."""
    _operar(rm, -abs(valor), symbol)


def ganhar(rm: RiskManager, valor: float, symbol: str = "PETR4") -> None:
    _operar(rm, abs(valor), symbol)


def _operar(rm: RiskManager, resultado: float, symbol: str) -> None:
    from cashinho.core.risk.models import Position, TradeResult

    quantidade = 100
    entrada = 10.0
    posicao = Position(
        symbol=symbol.upper(),
        direcao=Direction.LONG,
        quantidade=quantidade,
        preco_medio=entrada,
        stop=9.0,
        aberta_em=AGORA,
    )
    rm.estado.registrar_abertura(posicao)
    trade = TradeResult(
        symbol=symbol.upper(),
        direcao=Direction.LONG,
        quantidade=quantidade,
        preco_entrada=entrada,
        preco_saida=entrada + resultado / quantidade,
        custos=0.0,
        aberto_em=AGORA,
        fechado_em=AGORA,
    )
    rm.estado.registrar_fechamento(trade)
    rm._avaliar_travas_automaticas()
