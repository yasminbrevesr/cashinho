"""Persistencia: ida e volta entre dominio e banco."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from cashinho.adapters.persistence.repositories import AnalysisRunRepository, JournalRepository
from cashinho.adapters.persistence.session import resolve_database_url, session_scope
from cashinho.domain.enums import DataStatus, Mode, OpportunityState
from cashinho.domain.journal import AnalysisRun, JournalEntry
from cashinho.domain.quality import DataQualityReport
from tests.conftest import REFERENCE_INSTANT

pytestmark = pytest.mark.integration


def _entry(symbol: str = "PETR4", **kwargs: object) -> JournalEntry:
    base: dict[str, object] = {
        "symbol": symbol,
        "timestamp": REFERENCE_INSTANT,
        "mode": Mode.PAPER,
        "state": OpportunityState.NAO_OPERAR,
        "entry_reason": "contexto contrario",
    }
    base.update(kwargs)
    return JournalEntry(**base)  # type: ignore[arg-type]


def test_tabelas_criadas(sqlite_engine: Engine) -> None:
    tabelas = set(inspect(sqlite_engine).get_table_names())
    assert {"analysis_runs", "journal_entries"} <= tabelas


def test_gravacao_e_leitura_do_diario(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        JournalRepository(session).add(_entry())

    with session_factory() as session:
        entries = JournalRepository(session).list_recent()
    assert len(entries) == 1
    assert entries[0].symbol == "PETR4"
    assert entries[0].state is OpportunityState.NAO_OPERAR


def test_decimal_preserva_precisao(session_factory: sessionmaker[Session]) -> None:
    """Regressao: Numeric no SQLite viraria float e perderia centavos."""
    with session_scope(session_factory) as session:
        JournalRepository(session).add(
            _entry(entry=Decimal("38.71"), stop=Decimal("38.29"), result=Decimal("-127.53"))
        )

    with session_factory() as session:
        saved = JournalRepository(session).list_recent()[0]
    assert saved.entry == Decimal("38.71")
    assert isinstance(saved.entry, Decimal)
    assert saved.result == Decimal("-127.53")


def test_datetime_volta_com_fuso(session_factory: sessionmaker[Session]) -> None:
    """Regressao: DateTime no SQLite voltaria naive e quebraria o dominio."""
    with session_scope(session_factory) as session:
        JournalRepository(session).add(_entry())

    with session_factory() as session:
        saved = JournalRepository(session).list_recent()[0]
    assert saved.timestamp.tzinfo is not None
    assert saved.timestamp == REFERENCE_INSTANT


def test_ordenacao_por_data_decrescente(session_factory: sessionmaker[Session]) -> None:
    antigo = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    with session_scope(session_factory) as session:
        repo = JournalRepository(session)
        repo.add(_entry("VALE3", timestamp=antigo))
        repo.add(_entry("PETR4"))

    with session_factory() as session:
        entries = JournalRepository(session).list_recent()
    assert [e.symbol for e in entries] == ["PETR4", "VALE3"]


def test_filtro_por_ativo(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        repo = JournalRepository(session)
        repo.add(_entry("PETR4"))
        repo.add(_entry("VALE3"))

    with session_factory() as session:
        assert len(JournalRepository(session).list_by_symbol("petr4")) == 1


def test_rollback_em_caso_de_erro(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError), session_scope(session_factory) as session:
        JournalRepository(session).add(_entry())
        raise RuntimeError("falha simulada")

    with session_factory() as session:
        assert JournalRepository(session).count() == 0


def test_analysis_run_persiste_qualidade(session_factory: sessionmaker[Session]) -> None:
    run = AnalysisRun(
        id=uuid4(),
        mode=Mode.PAPER,
        started_at=REFERENCE_INSTANT,
        clock_kind="FrozenClock",
        code_version="0.1.0",
        config_hash="abc123",
        provider="fixture",
        symbol="PETR4",
        data_quality=DataQualityReport(
            symbol="PETR4",
            source="fixture",
            status=DataStatus.BLOCKED,
            checked_at=REFERENCE_INSTANT,
        ),
    )
    with session_scope(session_factory) as session:
        AnalysisRunRepository(session).add(run)

    with session_factory() as session:
        assert AnalysisRunRepository(session).count() == 1


def test_caminho_relativo_do_sqlite_e_resolvido(tmp_path: Path) -> None:
    url = resolve_database_url("sqlite:///data/cashinho.db", root=tmp_path)
    assert url.startswith("sqlite:////") or str(tmp_path) in url
    assert (tmp_path / "data").is_dir()


def test_memoria_nao_e_alterada() -> None:
    assert resolve_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
