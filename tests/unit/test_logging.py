"""Logging estruturado."""

from __future__ import annotations

import json
import logging

import pytest

from cashinho.observability.logging import (
    JsonFormatter,
    configure_logging,
    get_logger,
    reset_logging,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_logging()
    yield
    reset_logging()


def test_logger_fica_sob_o_namespace_cashinho() -> None:
    assert get_logger("cashinho.core.time").name == "cashinho.core.time"
    assert get_logger("core.time").name == "cashinho.core.time"


def test_configuracao_e_idempotente() -> None:
    configure_logging("INFO", "json")
    configure_logging("INFO", "json")
    assert len(logging.getLogger("cashinho").handlers) == 1


def test_formatter_json_serializa_campos_extras() -> None:
    record = logging.LogRecord(
        name="cashinho.teste",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="analise bloqueada",
        args=(),
        exc_info=None,
    )
    record.symbol = "PETR4"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "analise bloqueada"
    assert payload["symbol"] == "PETR4"
    assert payload["level"] == "INFO"
    assert payload["ts"].endswith("+00:00")
