"""Resolucao de simbolo: correspondencia exata primeiro.

A Genial expoe, para o mesmo papel:

    PETR4  PETR4F  PETR4T  PETR4M  PETR4Q  PETR4R

Procurar por `"PETR4" in nome` casa com os seis. Escolher um deles em silencio
significa analisar o fracionario, o termo ou a opcao achando que se analisou a
acao - erro caro e invisivel.

Regra: exata primeiro, e so ela e automatica. Sem exata, o resultado e erro
que **nomeia os candidatos**.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cashinho.domain.errors import CashinhoError


class SymbolNotFoundError(CashinhoError):
    """SYMBOL_NOT_FOUND: o ativo nao existe na corretora."""


class AmbiguousSymbolError(CashinhoError):
    """SYMBOL_AMBIGUOUS: ha mais de um candidato e nenhum exato."""


@dataclass(frozen=True)
class SymbolResolution:
    """O simbolo escolhido e **como** ele foi escolhido."""

    requested: str
    resolved: str
    exact: bool
    candidates: tuple[str, ...] = ()


def resolve_symbol(
    requested: str,
    available: Sequence[str],
    *,
    allow_prefix: bool = False,
) -> SymbolResolution:
    """Resolve o ticker contra a lista da corretora.

    `allow_prefix` so deve ser ligado por quem sabe o que quer: com ele, um
    unico candidato por prefixo e aceito; com mais de um, continua sendo
    ambiguidade.
    """
    target = (requested or "").strip().upper()
    if not target:
        raise SymbolNotFoundError("SYMBOL_NOT_FOUND: ticker vazio")

    names = [str(name).strip() for name in available if str(name).strip()]
    by_upper = {name.upper(): name for name in names}

    if target in by_upper:
        return SymbolResolution(target, by_upper[target], exact=True)

    candidates = tuple(sorted(name for name in names if name.upper().startswith(target)))
    if not candidates:
        raise SymbolNotFoundError(
            f"SYMBOL_NOT_FOUND: '{target}' nao esta entre os {len(names)} simbolos "
            "da corretora. Confira se ele esta na Observacao do Mercado (Ctrl+M)"
        )

    if allow_prefix and len(candidates) == 1:
        return SymbolResolution(target, candidates[0], exact=False, candidates=candidates)

    raise AmbiguousSymbolError(
        f"SYMBOL_AMBIGUOUS: '{target}' nao tem correspondencia exata e ha "
        f"{len(candidates)} candidato(s): {', '.join(candidates[:8])}. "
        "Informe o ticker completo - escolher por voce seria analisar um "
        "instrumento diferente do pedido"
    )
