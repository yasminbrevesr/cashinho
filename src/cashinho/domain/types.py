"""Tipos base compartilhados pelos modelos de dominio.

Duas invariantes sao impostas aqui, e nao por convencao:

1. Todo datetime do dominio e timezone-aware e normalizado para UTC.
   Datetime naive e rejeitado na validacao.
2. Valores financeiros usam Decimal quantizado. float so aparece
   dentro do pipeline numerico (pandas/numpy), com conversao explicita
   na fronteira.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer

PRICE_EXPONENT = Decimal("0.01")
"""Precos da B3 tem duas casas decimais."""

MONEY_EXPONENT = Decimal("0.01")


def ensure_utc(value: datetime) -> datetime:
    """Rejeita datetime naive e normaliza para UTC.

    Datetime sem fuso e a origem mais comum de erro silencioso em
    analise intradiaria. Preferimos falhar cedo e alto.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "datetime naive nao e aceito no dominio: informe o fuso "
            "(o dominio trabalha internamente em UTC)"
        )
    return value.astimezone(UTC)


def quantize_price(value: Decimal) -> Decimal:
    """Arredonda um preco para a precisao negociavel da B3."""
    return value.quantize(PRICE_EXPONENT, rounding=ROUND_HALF_UP)


def quantize_money(value: Decimal) -> Decimal:
    """Arredonda um valor financeiro para centavos."""
    return value.quantize(MONEY_EXPONENT, rounding=ROUND_HALF_UP)


UtcDatetime = Annotated[
    datetime,
    AfterValidator(ensure_utc),
    PlainSerializer(lambda v: v.isoformat(), return_type=str, when_used="json"),
]
"""Datetime obrigatoriamente aware, normalizado para UTC."""

Price = Annotated[
    Decimal,
    AfterValidator(quantize_price),
    PlainSerializer(str, return_type=str, when_used="json"),
]
"""Preco em Decimal com duas casas."""

Money = Annotated[
    Decimal,
    AfterValidator(quantize_money),
    PlainSerializer(str, return_type=str, when_used="json"),
]
"""Valor monetario em Decimal com duas casas."""


class DomainModel(BaseModel):
    """Base de todos os modelos de dominio.

    Imutavel por padrao: um Candle ou uma RiskDecision nao devem ser
    alterados depois de criados. Mudanca de estado gera novo objeto,
    o que mantem o rastro auditavel.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )
