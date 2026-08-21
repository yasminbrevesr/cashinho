"""Fibonacci ancorado em swing objetivo.

A grade so nasce a partir de uma perna que o algoritmo classificou como
valida: dois pivos alternados, ambos confirmados, com amplitude acima do
limiar em ATR. Nao existe "puxar o Fibonacci" a mao aqui - sem swing valido,
nao ha grade (``FibGrid is None``) e o motivo fica registrado.

Convencao de ancoragem: **0% no extremo da perna** (de onde o preco corrige) e
**100% na origem**. Assim, retracao de 61,8% em uma perna de alta e' o preco
que devolveu 61,8% do movimento, e a extensao de 161,8% projeta o alvo alem
do topo.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Direction
from .config import PADRAO, EstruturaConfig
from .models import FibGrid, FibLevel, FibZone, Level, Swing

ZONAS = (
    ("rasa", 0.236, 0.382, "correcao rasa - tendencia forte, entrada agressiva"),
    ("nobre", 0.382, 0.618, "zona nobre - melhor relacao risco/retorno no pullback"),
    ("profunda", 0.618, 0.786, "correcao profunda - ainda valida, exige confirmacao"),
    ("alvos", 1.272, 1.618, "projecao de alvos da perna"),
)
"""As faixas da area de pullback (23,6% a 78,6%) sao continuas de proposito:
qualquer correcao dentro delas cai em exatamente uma zona."""


def rotulo(razao: float) -> str:
    return f"{razao * 100:.1f}%".replace(".0%", "%")


def preco_da_razao(swing: Swing, razao: float) -> float:
    """Preco correspondente a uma razao: <=1 retrai a perna, >1 projeta alem dela."""
    origem = swing.inicio.preco
    extremo = swing.fim.preco
    amplitude = extremo - origem  # com sinal
    if razao <= 1.0:
        return extremo - amplitude * razao
    return origem + amplitude * razao


def constroi(
    swing: Optional[Swing],
    niveis: Sequence[Level] = (),
    atr: float = 0.0,
    cfg: EstruturaConfig = PADRAO,
) -> Optional[FibGrid]:
    """Monta a grade se - e somente se - houver swing valido."""
    if swing is None or not swing.valido:
        return None

    tolerancia = atr * cfg.fib_confluencia_atr

    retracoes = tuple(
        FibLevel(
            razao=r,
            rotulo=rotulo(r),
            preco=preco_da_razao(swing, r),
            tipo="retracao",
            confluencia=confluencia(preco_da_razao(swing, r), niveis, tolerancia),
        )
        for r in sorted(cfg.retracoes)
    )
    extensoes = tuple(
        FibLevel(
            razao=e,
            rotulo=rotulo(e),
            preco=preco_da_razao(swing, e),
            tipo="extensao",
            confluencia=confluencia(preco_da_razao(swing, e), niveis, tolerancia),
        )
        for e in sorted(cfg.extensoes)
    )

    razoes_disponiveis = set(cfg.retracoes) | set(cfg.extensoes)
    zonas = tuple(
        _zona(swing, nome, inicio, fim, descricao)
        for nome, inicio, fim, descricao in ZONAS
        if inicio in razoes_disponiveis and fim in razoes_disponiveis
    )

    return FibGrid(
        swing=swing,
        ancora_0=swing.fim.preco,
        ancora_100=swing.inicio.preco,
        retracoes=retracoes,
        extensoes=extensoes,
        zonas=zonas,
    )


def _zona(swing: Swing, nome: str, razao_inicio: float, razao_fim: float, descricao: str) -> FibZone:
    a = preco_da_razao(swing, razao_inicio)
    b = preco_da_razao(swing, razao_fim)
    return FibZone(
        nome=nome,
        low=min(a, b),
        high=max(a, b),
        razao_inicio=razao_inicio,
        razao_fim=razao_fim,
        descricao=descricao,
    )


def confluencia(preco: float, niveis: Sequence[Level], tolerancia: float) -> Optional[Level]:
    """Nivel de suporte/resistencia que coincide com o preco do Fibonacci."""
    candidatos = [
        n for n in niveis if n.contem(preco) or n.distancia(preco) <= max(tolerancia, 0.0)
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda n: n.forca)


def motivo_da_ausencia(swings: Sequence[Swing], tem_pivos: bool) -> str:
    """Explica, em portugues, por que nao ha grade de Fibonacci."""
    if not tem_pivos:
        return "sem pivos confirmados: candles insuficientes para identificar um swing"
    if not swings:
        return "pivos confirmados, mas nenhuma perna alternada formada ainda"
    ultimo = swings[-1]
    return (
        "nenhuma perna atingiu a amplitude minima para virar swing valido "
        f"(ultima: {ultimo.motivo or 'amplitude insuficiente'})"
    )
