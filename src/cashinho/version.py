"""Versao do codigo. Registrada em cada AnalysisRun para reprodutibilidade."""

from __future__ import annotations

__version__ = "0.1.0"


def code_version() -> str:
    """Identificador da versao do codigo usada em auditoria."""
    return __version__
