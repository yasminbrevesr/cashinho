"""Do conjunto de leituras para uma palavra: o regime de mercado.

A classificacao e' explicita e pequena de proposito - da para ler as regras
inteiras em trinta segundos e discordar delas. Um regime que sai de um modelo
opaco nao ajudaria ninguem a decidir se confia nele.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .modelos import (
    DirecaoDeMercado,
    Leitura,
    NivelDeVolatilidade,
    RegimeDeMercado,
)


def classificar_regime(
    ibovespa: Optional[Leitura],
    dolar: Optional[Leitura],
    volatilidade: NivelDeVolatilidade,
    internacionais: Sequence[Leitura] = (),
) -> tuple[RegimeDeMercado, tuple[str, ...]]:
    """Devolve o regime e as frases que o justificam."""
    motivos: list[str] = []

    if ibovespa is None or not ibovespa.mensuravel:
        return RegimeDeMercado.INDEFINIDO, (
            "sem leitura utilizavel do Ibovespa: nao da para afirmar regime nenhum",
        )

    direcao = ibovespa.direcao
    if not direcao.conhecida:
        return RegimeDeMercado.INDEFINIDO, (
            "Ibovespa sem variacao calculavel no periodo",
        )
    motivos.append(f"Ibovespa em {direcao.rotulo.lower()} ({ibovespa.variacao_pct:+.2f}%)")

    # volatilidade fora do normal domina: o ambiente esta caro de operar,
    # independente da direcao do indice
    if volatilidade is NivelDeVolatilidade.EXTREMA:
        motivos.append("volatilidade extrema contra o proprio historico do indice")
        return RegimeDeMercado.ESTRESSE, tuple(motivos)
    if volatilidade is NivelDeVolatilidade.ALTA and direcao is DirecaoDeMercado.BAIXA:
        motivos.append("queda com volatilidade alta")
        return RegimeDeMercado.ESTRESSE, tuple(motivos)

    direcao_dolar = (dolar.direcao if (dolar and dolar.mensuravel)
                     else DirecaoDeMercado.INDISPONIVEL)
    if direcao_dolar.conhecida:
        motivos.append(f"dolar em {direcao_dolar.rotulo.lower()} ({dolar.variacao_pct:+.2f}%)")
    else:
        motivos.append("sem leitura de dolar: regime definido so pelo indice")

    alinhamento = _alinhamento_internacional(internacionais)
    if alinhamento:
        motivos.append(alinhamento)

    if direcao is DirecaoDeMercado.LATERAL:
        return RegimeDeMercado.LATERAL, tuple(motivos)

    # bolsa e dolar subindo (ou caindo) juntos e' sinal misto: no Brasil os
    # dois costumam andar em sentidos opostos, e quando nao andam a leitura
    # de ambiente perde forca
    if direcao is DirecaoDeMercado.ALTA:
        if direcao_dolar is DirecaoDeMercado.ALTA:
            motivos.append("bolsa e dolar subindo juntos")
            return RegimeDeMercado.CONFLITANTE, tuple(motivos)
        return RegimeDeMercado.RISCO_LIGADO, tuple(motivos)

    if direcao_dolar is DirecaoDeMercado.BAIXA:
        motivos.append("bolsa caindo com dolar em queda")
        return RegimeDeMercado.CONFLITANTE, tuple(motivos)
    return RegimeDeMercado.RISCO_DESLIGADO, tuple(motivos)


def _alinhamento_internacional(leituras: Sequence[Leitura]) -> str:
    """Os indices de fora estao todos no mesmo sentido?"""
    direcoes = [l.direcao for l in leituras if l.mensuravel and l.direcao.conhecida]
    if not direcoes:
        return ""
    altas = sum(1 for d in direcoes if d is DirecaoDeMercado.ALTA)
    baixas = sum(1 for d in direcoes if d is DirecaoDeMercado.BAIXA)
    if altas and not baixas:
        return f"{altas} indice(s) internacional(is) em alta"
    if baixas and not altas:
        return f"{baixas} indice(s) internacional(is) em baixa"
    return "indices internacionais divididos"
