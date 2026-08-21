"""Instrumento negociavel."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from cashinho.domain.types import DomainModel

_B3_TICKER = re.compile(r"^[A-Z]{4}\d{1,2}$")
"""Formato de ticker da B3: quatro letras seguidas de um ou dois digitos."""


class Instrument(DomainModel):
    """Ativo negociavel na B3.

    `lot_size` existe porque o dimensionamento de posicao precisa
    respeitar o lote-padrao; arredondar isso na interface seria perder
    a rastreabilidade da restricao que limitou a quantidade.
    """

    symbol: str = Field(description="Ticker da B3, ex.: PETR4")
    name: str = Field(default="", description="Nome do ativo")
    lot_size: int = Field(default=100, gt=0, description="Lote-padrao")
    tick_size: str = Field(default="0.01", description="Variacao minima de preco")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        upper = value.upper()
        if not _B3_TICKER.match(upper):
            raise ValueError(
                f"ticker fora do formato esperado da B3: {value!r} "
                "(esperado quatro letras e um ou dois digitos, ex.: PETR4)"
            )
        return upper

    def __str__(self) -> str:
        return self.symbol
