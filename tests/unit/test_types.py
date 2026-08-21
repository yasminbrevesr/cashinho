"""Invariantes de tipo: datetime aware e Decimal quantizado."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from cashinho.domain.types import (
    DomainModel,
    Price,
    UtcDatetime,
    ensure_utc,
    quantize_money,
    quantize_price,
)


def test_datetime_naive_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="naive"):
        ensure_utc(datetime(2026, 8, 20, 14, 0))


def test_datetime_com_fuso_e_convertido_para_utc() -> None:
    sao_paulo = timezone(timedelta(hours=-3))
    result = ensure_utc(datetime(2026, 8, 20, 14, 0, tzinfo=sao_paulo))
    assert result.tzinfo is UTC
    assert result.hour == 17


def test_modelo_rejeita_datetime_naive() -> None:
    class Sample(DomainModel):
        moment: UtcDatetime

    with pytest.raises(ValueError, match="naive"):
        Sample(moment=datetime(2026, 8, 20, 14, 0))


def test_preco_e_quantizado_em_duas_casas() -> None:
    class Sample(DomainModel):
        value: Price

    assert Sample(value=Decimal("10.126")).value == Decimal("10.13")
    assert Sample(value=Decimal("10.124")).value == Decimal("10.12")


def test_quantizacao_usa_half_up() -> None:
    assert quantize_price(Decimal("10.125")) == Decimal("10.13")
    assert quantize_money(Decimal("0.005")) == Decimal("0.01")


def test_modelo_de_dominio_e_imutavel() -> None:
    class Sample(DomainModel):
        value: Price

    sample = Sample(value=Decimal("10.00"))
    with pytest.raises(ValidationError):
        sample.value = Decimal("11.00")


def test_modelo_de_dominio_rejeita_campo_desconhecido() -> None:
    class Sample(DomainModel):
        value: Price

    with pytest.raises(ValidationError):
        Sample(value=Decimal("10.00"), desconhecido=1)
