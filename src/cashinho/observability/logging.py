"""Logging estruturado.

Stdlib apenas — sem dependencia adicional. Dois formatos:

- `console`: legivel, para desenvolvimento
- `json`:    uma linha por evento, para auditoria e analise posterior

Campos extras entram por `logger.info("evento", extra={"symbol": "PETR4"})`
e sao serializados no JSON.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }
)

_configured = False


class JsonFormatter(logging.Formatter):
    """Serializa cada registro como uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configura o logging do processo. Idempotente.

    Idempotencia importa: o Streamlit reexecuta o script a cada interacao
    e sem essa guarda os handlers se acumulariam a cada rerun.
    """
    global _configured
    root = logging.getLogger("cashinho")
    if _configured:
        root.setLevel(level.upper())
        return

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Logger nomeado sob o namespace `cashinho`."""
    suffix = name.removeprefix("cashinho.")
    return logging.getLogger(f"cashinho.{suffix}")


def reset_logging() -> None:
    """Reinicia a configuracao. Uso restrito a testes."""
    global _configured
    logging.getLogger("cashinho").handlers.clear()
    _configured = False
