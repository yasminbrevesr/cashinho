"""Formatadores de tela - numero, percentual, hora e barra.

Cada um existia em duas a quatro copias, com casas decimais e simbolos
ligeiramente diferentes. A diferenca aparecia como "-0,00%" numa tela e
"0.00%" na outra, no mesmo numero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ...models import formata_dinheiro

__all__ = ["num", "pct", "hora", "barra", "formata_dinheiro", "ou_traco"]

TRACO = "-"


def ou_traco(valor: Optional[object]) -> str:
    """``None`` vira travessao. Nunca zero: zero e' uma afirmacao."""
    return TRACO if valor is None else str(valor)


def num(valor: Optional[float], casas: int = 2, sufixo: str = "",
        sinal: bool = False) -> str:
    """Numero no padrao brasileiro (virgula decimal), ou ``-`` se ausente."""
    if valor is None:
        return TRACO
    formato = f"{{:{'+' if sinal else ''}.{casas}f}}"
    return formato.format(valor).replace(".", ",") + sufixo


def pct(valor: Optional[float], casas: int = 2, sinal: bool = True) -> str:
    """Percentual. ``-0,00%`` vira ``0,00%``: o sinal negativo em zero mente."""
    if valor is None:
        return TRACO
    if abs(valor) < 10 ** (-casas) / 2:
        valor = 0.0
    return num(valor, casas, "%", sinal=sinal and valor != 0)


def hora(ts: Optional[datetime], referencia: Optional[datetime] = None,
         segundos: bool = False) -> str:
    """``14:30`` no mesmo dia, ``21/08 14:30`` em outro."""
    if ts is None:
        return TRACO
    formato = "%H:%M:%S" if segundos else "%H:%M"
    if referencia is not None and ts.date() != referencia.date():
        return ts.strftime("%d/%m " + formato)
    return ts.strftime(formato)


def barra(fracao: float, largura: int = 10, cheio: str = "█", vazio: str = "·") -> str:
    """Barra de proporcao. ``fracao`` de 0 a 1, presa nesse intervalo."""
    fracao = max(0.0, min(1.0, fracao))
    cheias = int(round(fracao * largura))
    return cheio * cheias + vazio * (largura - cheias)


def barra_de_nota(nota: float, largura: int = 10) -> str:
    """Barra para nota de 0 a 100."""
    return barra(nota / 100.0, largura)
