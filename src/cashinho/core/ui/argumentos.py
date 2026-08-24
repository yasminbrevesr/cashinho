"""Parsers de argumento de linha de comando, compartilhados pelas CLIs.

``--data``, ``--fim-treino``, ``--abrir-em``: seis CLIs tinham o mesmo
``_data()``, cada uma com uma mensagem de erro diferente para o mesmo engano.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from typing import Optional

from ...models import BRT


def data(texto: str) -> date:
    """``AAAA-MM-DD`` -> :class:`date`."""
    try:
        return date.fromisoformat(texto.strip())
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"data invalida: {texto!r} (use AAAA-MM-DD)") from e


def instante(texto: str) -> datetime:
    """``AAAA-MM-DDTHH:MM`` -> :class:`datetime` no fuso de Brasilia."""
    try:
        ts = datetime.fromisoformat(texto.strip())
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"data/hora invalida: {texto!r} (use AAAA-MM-DDTHH:MM)") from e
    return ts.replace(tzinfo=BRT) if ts.tzinfo is None else ts


def hora(texto: str) -> Optional[time]:
    """``HH:MM`` -> :class:`time`. Vazio vira ``None``."""
    texto = texto.strip()
    if not texto:
        return None
    try:
        return time.fromisoformat(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"horario invalido: {texto!r} (use HH:MM)") from e


def percentuais(texto: str) -> tuple[float, ...]:
    """``60,20,20`` ou ``0.6,0.2,0.2`` -> fracoes que somam 1.

    Aceita as duas escalas usuais e recusa o resto: reescalar qualquer soma
    seria conveniente e silencioso, e a divisao pedida nao seria a feita.
    """
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    try:
        valores = [float(p) for p in partes]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"percentuais invalidos: {texto!r}") from e
    if not valores:
        raise argparse.ArgumentTypeError("informe ao menos um percentual")
    if any(v <= 0 for v in valores):
        raise argparse.ArgumentTypeError("nenhuma fatia pode ficar com zero")

    total = sum(valores)
    if abs(total - 1.0) < 1e-6:
        escala = 1.0
    elif abs(total - 100.0) < 1e-6:
        escala = 100.0
    else:
        raise argparse.ArgumentTypeError(
            f"os percentuais somam {total:g}: use fracoes que somem 1 "
            "(0.6,0.2,0.2) ou porcentagens que somem 100 (60,20,20)")
    return tuple(v / escala for v in valores)
