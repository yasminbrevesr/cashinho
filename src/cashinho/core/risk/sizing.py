"""Calculo do tamanho da posicao - funcoes puras, sem estado e sem estrategia.

    risco monetario = capital x percentual de risco
    risco por acao  = abs(entrada - stop)
    quantidade      = floor(risco monetario / risco por acao)

e, em seguida, o corte pelos limites de capital e de exposicao. Todo
arredondamento e' para BAIXO: na duvida, o robo arrisca menos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .models import Limitador

EPS = 1e-9


def piso(valor: float) -> int:
    """Floor tolerante a ruido de ponto flutuante (299.9999999997 -> 300)."""
    return int(math.floor(valor + EPS))


def risco_monetario(capital: float, percentual: float, teto: Optional[float] = None) -> float:
    """capital x percentual, limitado pelo teto absoluto quando houver."""
    valor = capital * percentual / 100.0
    if teto is not None:
        valor = min(valor, teto)
    return max(valor, 0.0)


def risco_por_acao(entrada: float, stop: float) -> float:
    return abs(entrada - stop)


def quantidade_por_risco(risco_monetario_: float, risco_por_acao_: float) -> int:
    """floor(risco monetario / risco por acao). Risco por acao zero nao dimensiona."""
    if risco_por_acao_ <= 0:
        raise ZeroDivisionError("risco por acao igual a zero: entrada e stop no mesmo preco")
    if risco_monetario_ <= 0:
        return 0
    return piso(risco_monetario_ / risco_por_acao_)


def quantidade_por_financeiro(financeiro_disponivel: float, preco: float) -> int:
    """Quantas acoes cabem em um valor financeiro."""
    if preco <= 0:
        raise ValueError("preco precisa ser maior que zero")
    if financeiro_disponivel <= 0:
        return 0
    return piso(financeiro_disponivel / preco)


def ajusta_ao_lote(quantidade: int, lote: int, permitir_fracionario: bool) -> int:
    """Sem mercado fracionario, so multiplos do lote padrao passam."""
    if quantidade <= 0:
        return 0
    if permitir_fracionario:
        return quantidade
    return (quantidade // lote) * lote


@dataclass(frozen=True)
class Dimensionamento:
    quantidade: int
    limitador: Limitador
    risco_alvo: float
    risco_por_acao: float
    risco_efetivo: float
    exposicao: float
    candidatos: dict[str, int] = field(default_factory=dict)

    @property
    def zerado(self) -> bool:
        return self.quantidade <= 0


def dimensionar(
    entrada: float,
    stop: float,
    risco_alvo: float,
    caixa_disponivel: float,
    teto_ativo_restante: float,
    teto_total_restante: float,
    lote: int = 100,
    permitir_fracionario: bool = True,
    limitador_do_risco: Limitador = Limitador.RISCO,
) -> Dimensionamento:
    """Aplica, em ordem, o risco e depois os cortes de capital e exposicao.

    O ``limitador`` devolvido diz qual restricao definiu o tamanho - e' o que
    a pagina de risco mostra para explicar por que a quantidade ficou naquele
    numero.
    """
    if entrada <= 0:
        raise ValueError("entrada precisa ser maior que zero")

    rpa = risco_por_acao(entrada, stop)
    candidatos = {
        limitador_do_risco.name: quantidade_por_risco(risco_alvo, rpa),
        Limitador.CAPITAL.name: quantidade_por_financeiro(caixa_disponivel, entrada),
        Limitador.EXPOSICAO_ATIVO.name: quantidade_por_financeiro(teto_ativo_restante, entrada),
        Limitador.EXPOSICAO_TOTAL.name: quantidade_por_financeiro(teto_total_restante, entrada),
    }

    # a ordem do empate importa: o risco explica melhor que o capital
    ordem = (
        limitador_do_risco,
        Limitador.CAPITAL,
        Limitador.EXPOSICAO_ATIVO,
        Limitador.EXPOSICAO_TOTAL,
    )
    bruto = min(candidatos.values())
    limitador = next(l for l in ordem if candidatos[l.name] == bruto)

    quantidade = ajusta_ao_lote(bruto, lote, permitir_fracionario)
    return Dimensionamento(
        quantidade=quantidade,
        limitador=limitador,
        risco_alvo=risco_alvo,
        risco_por_acao=rpa,
        risco_efetivo=quantidade * rpa,
        exposicao=quantidade * entrada,
        candidatos=candidatos,
    )
