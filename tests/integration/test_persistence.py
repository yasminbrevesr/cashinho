"""Persistencia: ida e volta entre dominio e banco."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from cashinho.adapters.persistence.repositories import AnalysisRunRepository, JournalRepository
from cashinho.adapters.persistence.session import resolve_database_url, session_scope
from cashinho.domain.enums import DataStatus, Mode, OpportunityState, Timeframe
from cashinho.domain.journal import AnalysisRun, JournalEntry
from cashinho.domain.market import Candle, CandleSeries
from cashinho.domain.quality import DataQualityReport
from cashinho.pipeline.final_decision import FinalDecision
from cashinho.pipeline.journal_audit import JournalAuditService
from cashinho.pipeline.paper_broker import (
    InMemoryPaperOrderRepository,
    PaperBroker,
    PaperOrderStatus,
    PaperOrderType,
)
from cashinho.pipeline.paper_ticket import build_paper_ticket
from cashinho.pipeline.position_manager import (
    PositionAction,
    PositionManager,
    PositionRiskState,
    apply_position_decision,
)
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
    assert {
        "analysis_runs",
        "journal_entries",
        "decision_journal",
        "paper_trade_journal",
        "paper_order_events",
        "position_decision_journal",
    } <= tabelas


def test_final_decision_e_registrada_com_idempotencia(
    session_factory: sessionmaker[Session],
) -> None:
    decision = FinalDecision(
        should_enter=False,
        side="NONE",
        symbol="PETR4",
        timeframe=Timeframe.M5,
        confidence=42,
        entry=None,
        stop=None,
        target=None,
        risk_reward=None,
        primary_reason="Gatilho ausente.",
        reasons=("Gatilho ausente.",),
        timestamp=REFERENCE_INSTANT,
    )
    audit = JournalAuditService(session_factory)
    assert audit.record_decision(decision)
    assert not audit.record_decision(decision)
    with session_factory() as session:
        records = JournalRepository(session).list_recent_decisions()
    assert len(records) == 1
    assert records[0].primary_reason == "Gatilho ausente."


def test_contagem_de_entradas_liberadas_usa_banco_completo(
    session_factory: sessionmaker[Session],
) -> None:
    decision = FinalDecision(
        should_enter=True,
        side="BUY",
        symbol="PETR4",
        timeframe=Timeframe.M5,
        confidence=80,
        entry=Decimal("10"),
        stop=Decimal("9"),
        target=Decimal("12"),
        risk_reward=2.0,
        primary_reason="Aprovada.",
        reasons=("Aprovada.",),
        timestamp=REFERENCE_INSTANT,
    )
    JournalAuditService(session_factory).record_decision(decision)
    start = REFERENCE_INSTANT.replace(hour=0, minute=0, second=0, microsecond=0)
    with session_factory() as session:
        count = JournalRepository(session).count_released_decisions(
            start=start, end=start + timedelta(days=1)
        )
    assert count == 1


def test_ordem_aberta_e_encerrada_atualiza_diario(
    session_factory: sessionmaker[Session],
) -> None:
    audit = JournalAuditService(session_factory)
    broker = PaperBroker(InMemoryPaperOrderRepository(), observer=audit)
    ticket = build_paper_ticket(
        symbol="PETR4",
        side="BUY",
        entry=Decimal("10"),
        stop=Decimal("9"),
        target=Decimal("12"),
        quantity=10,
        timeframe="5m",
    )
    created = broker.register(
        ticket,
        PaperOrderType.LIMIT,
        now=REFERENCE_INSTANT - timedelta(minutes=10),
    )
    opened = Candle(
        open_time=REFERENCE_INSTANT,
        close_time=REFERENCE_INSTANT + timedelta(minutes=5),
        open=Decimal("10"),
        high=Decimal("10.5"),
        low=Decimal("9.5"),
        close=Decimal("10"),
        volume=100,
    )
    assert broker.process_candle(opened)[0].status is PaperOrderStatus.OPEN
    with session_factory() as session:
        opened_record = JournalRepository(session).list_recent_paper_trades()[0]
    assert opened_record.status == "OPEN"
    assert opened_record.fill_price == Decimal("10")
    broker.close_position(
        created.id,
        price=Decimal("11"),
        closed_at=REFERENCE_INSTANT + timedelta(minutes=15),
    )

    with session_factory() as session:
        records = JournalRepository(session).list_recent_paper_trades()
    assert len(records) == 1
    assert records[0].status == "CLOSED"
    assert records[0].pnl_value == Decimal("10.00")
    assert records[0].result_in_r == Decimal("1.00")


def test_ciclo_integrado_decisao_posicao_saida_pnl_e_diario(
    session_factory: sessionmaker[Session],
) -> None:
    audit = JournalAuditService(session_factory)
    entry_decision = FinalDecision(
        should_enter=True,
        side="BUY",
        symbol="PETR4",
        timeframe=Timeframe.M5,
        confidence=84,
        entry=Decimal("10"),
        stop=Decimal("9"),
        target=Decimal("12"),
        risk_reward=2.0,
        primary_reason="Entrada aprovada.",
        reasons=("Gatilho confirmado.",),
        timestamp=REFERENCE_INSTANT - timedelta(minutes=10),
    )
    assert audit.record_decision(entry_decision)

    broker = PaperBroker(InMemoryPaperOrderRepository(), observer=audit)
    order = broker.register(
        build_paper_ticket(
            symbol="PETR4",
            side="BUY",
            entry=Decimal("10"),
            stop=Decimal("9"),
            target=Decimal("12"),
            quantity=10,
            timeframe="5m",
        ),
        PaperOrderType.LIMIT,
        now=entry_decision.timestamp,
    )
    opening_candle = Candle(
        open_time=REFERENCE_INSTANT - timedelta(minutes=5),
        close_time=REFERENCE_INSTANT,
        open=Decimal("10"),
        high=Decimal("10.4"),
        low=Decimal("9.6"),
        close=Decimal("10.2"),
        volume=100,
    )
    opened = broker.process_candle(opening_candle)[0]
    candles = CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=(opening_candle,),
        source="test",
        fetched_at=REFERENCE_INSTANT,
    )
    position_decision = PositionManager().evaluate(
        opened,
        recent_candles=candles,
        technical_signal=None,
        timeframe_advice=None,
        risk=PositionRiskState(True, "Risk Manager exigiu saída."),
        current_price=Decimal("11"),
        market_exit_price=Decimal("11"),
    )
    assert position_decision.action is PositionAction.EXIT
    assert audit.record_position_decision(order.id, position_decision)
    assert not audit.record_position_decision(order.id, position_decision)
    closed = apply_position_decision(broker, opened, position_decision)
    assert closed is not None
    assert closed.close_reason == "RISK_EXIT"

    with session_factory() as session:
        repository = JournalRepository(session)
        assert repository.list_recent_decisions()[0].should_enter
        assert repository.list_recent_position_decisions()[0].action == "EXIT"
        events = repository.list_recent_paper_order_events()
        trade = repository.list_recent_paper_trades()[0]
    assert {event.status for event in events} >= {"PENDING", "OPEN", "CLOSED"}
    assert trade.status == "CLOSED"
    assert trade.pnl_value == Decimal("10.00")
    assert trade.result_in_r == Decimal("1.00")


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
