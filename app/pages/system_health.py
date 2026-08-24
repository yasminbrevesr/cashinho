"""System Health — estado tecnico verificavel."""

from __future__ import annotations

from datetime import UTC

import streamlit as st

from app.components.chrome import page_header, sidebar
from app.components.feed import render_feed_status
from cashinho.adapters.persistence.session import (
    create_db_engine,
    init_db,
    resolve_database_url,
)
from cashinho.adapters.providers.factory import build_market_data_provider
from cashinho.config.settings import get_settings
from cashinho.core.time.b3_calendar import B3Calendar
from cashinho.core.time.clocks import SystemClock
from cashinho.version import __version__

MONITORED_SYMBOL = "PETR4"
"""Ativo usado para verificar o feed. Primeiro papel integrado ao MT5."""

settings = get_settings()
sidebar(settings)
page_header("System Health", "Estado tecnico verificavel do sistema")

clock = SystemClock()
calendar = B3Calendar()
now = clock.now()

col1, col2, col3 = st.columns(3)
col1.metric("Versao do codigo", __version__)
col2.metric("Relogio", clock.kind)
col3.metric("Hash da configuracao", settings.config_hash())

st.subheader("Tempo")
st.write(f"Instante logico (UTC): `{now.isoformat()}`")
st.write(f"Horario local da B3: `{calendar.to_local(now).strftime('%d/%m/%Y %H:%M:%S')}`")
if calendar.is_open(now):
    st.success("Pregao regular aberto.", icon="🟢")
else:
    st.info("Pregao regular fechado.", icon="🔴")
if not calendar.holidays_loaded:
    st.warning(
        "Calendario de feriados da B3 nao carregado. Dias uteis sao aproximados "
        "ate a integracao de uma fonte oficial (Fase 2).",
        icon="⚠️",
    )

st.subheader("Banco de dados")
try:
    engine = create_db_engine(settings)
    init_db(engine)
    st.success(f"Conectado: `{resolve_database_url(settings.database_url)}`", icon="✅")
except Exception as exc:  # a tela deve mostrar a falha, nao quebrar
    st.error(f"Falha ao conectar: {exc}", icon="⛔")

st.subheader("Dados de mercado")
choice = build_market_data_provider(settings, clock)
st.write(f"Provider ativo: `{choice.provider.capabilities.name}` — {choice.reason}")
render_feed_status(choice, MONITORED_SYMBOL, settings.display_timezone)
st.caption(
    "O Cashinho nao inventa cotacoes e nao apresenta preco antigo como atual. "
    "Fonte sem tempo real nao habilita decisao ao vivo."
)

st.caption(f"Fuso interno: UTC · exibicao: {settings.display_timezone} · agora {now.astimezone(UTC).isoformat()}")
