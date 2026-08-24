"""Resolucao de simbolo - correspondencia exata primeiro.

A Genial expoe, para um mesmo papel:

    PETR4  PETR4F  PETR4T  PETR4M  PETR4Q  PETR4R

Procurar por ``"PETR4" in nome`` casa com os seis. Escolher um deles em
silencio significa analisar um instrumento e o operador achar que analisou
outro - fracionario, termo ou opcao no lugar da acao.

Regra: **exata primeiro**. Sem exata, e' erro que nomeia os candidatos - nunca
uma escolha automatica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..base import DataError


class SimboloNaoEncontradoError(DataError):
    """SYMBOL_NOT_FOUND: o ativo nao existe na corretora."""


class SimboloAmbiguoError(DataError):
    """SYMBOL_AMBIGUOUS: mais de um candidato e nenhum exato."""


@dataclass(frozen=True)
class Resolucao:
    """O simbolo escolhido e como ele foi escolhido."""

    pedido: str
    resolvido: str
    exato: bool
    candidatos: tuple[str, ...] = ()

    def para_dict(self) -> dict:
        return {"pedido": self.pedido, "resolvido": self.resolvido,
                "exato": self.exato, "candidatos": list(self.candidatos)}


def resolver(pedido: str, disponiveis: Sequence[str],
             permitir_aproximado: bool = False) -> Resolucao:
    """Resolve o ticker contra a lista da corretora.

    ``permitir_aproximado`` so deve ser ligado por quem sabe o que quer: com
    ele, um unico candidato por prefixo e' aceito; com mais de um, continua
    sendo ambiguidade.
    """
    alvo = (pedido or "").strip().upper()
    if not alvo:
        raise SimboloNaoEncontradoError("SYMBOL_NOT_FOUND: ticker vazio")

    nomes = [str(n).strip() for n in disponiveis if str(n).strip()]
    por_maiusculo = {n.upper(): n for n in nomes}

    # 1. exata - o caminho normal, e o unico automatico
    if alvo in por_maiusculo:
        return Resolucao(alvo, por_maiusculo[alvo], exato=True)

    # 2. candidatos por prefixo, so para explicar a falha
    candidatos = tuple(sorted(n for n in nomes if n.upper().startswith(alvo)))
    if not candidatos:
        raise SimboloNaoEncontradoError(
            f"SYMBOL_NOT_FOUND: '{alvo}' nao esta entre os {len(nomes)} simbolos "
            "da corretora. Confira se ele esta na Observacao do Mercado (Ctrl+M)")

    if permitir_aproximado and len(candidatos) == 1:
        return Resolucao(alvo, candidatos[0], exato=False, candidatos=candidatos)

    raise SimboloAmbiguoError(
        f"SYMBOL_AMBIGUOUS: '{alvo}' nao tem correspondencia exata e ha "
        f"{len(candidatos)} candidato(s): {', '.join(candidatos[:8])}. "
        "Informe o ticker completo - escolher por voce seria analisar um "
        "instrumento diferente do que voce pediu")
