"""Composição compartilhada dos serviços persistentes da interface."""

from __future__ import annotations

import streamlit as st

from cashinho.adapters.persistence.session import (
    SessionFactory,
    build_session_factory,
    create_db_engine,
    init_db,
)
from cashinho.config.settings import get_settings
from cashinho.pipeline.journal_audit import JournalAuditService
from cashinho.pipeline.paper_broker import JsonPaperOrderRepository, PaperBroker


@st.cache_resource
def journal_session_factory() -> SessionFactory:
    engine = create_db_engine(get_settings())
    init_db(engine)
    return build_session_factory(engine)


def build_paper_broker() -> tuple[PaperBroker, JournalAuditService]:
    settings = get_settings()
    audit = journal_audit_service()
    broker = PaperBroker(
        JsonPaperOrderRepository(settings.data_dir / "paper_orders.json"),
        observer=audit,
    )
    audit.sync_orders(broker.list_orders())
    return broker, audit


def journal_audit_service() -> JournalAuditService:
    settings = get_settings()
    return JournalAuditService(journal_session_factory(), settings.mode)
