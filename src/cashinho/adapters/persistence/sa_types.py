"""Tipos SQLAlchemy customizados.

O SQLite nao tem tipo nativo de data com fuso nem tipo decimal exato.
Duas consequencias que corromperiam invariantes do dominio:

1. `DateTime` gravaria o valor e devolveria naive, quebrando a regra de
   datetime sempre aware.
2. `Numeric` seria armazenado como float, reintroduzindo o drift de
   centavos que a decisao D6 elimina.

Ambos sao resolvidos gravando texto e reconstruindo o tipo na leitura.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Dialect, String, TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Datetime aware persistido como ISO-8601 em UTC."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime naive nao pode ser persistido")
        return value.astimezone(UTC).isoformat()

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:  # pragma: no cover - dado legado
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)


class DecimalText(TypeDecorator[Decimal]):
    """Decimal persistido como texto, sem conversao para float."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)
