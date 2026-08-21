"""Configuracoes efetivas."""

from __future__ import annotations

import streamlit as st

from app.components.chrome import page_header, placeholder, sidebar
from cashinho.config.settings import IMPLEMENTED_MODES, get_settings

settings = get_settings()
sidebar(settings)
page_header("Configurações", "Configuracao efetiva carregada do ambiente")

st.warning(
    "Somente leitura. A configuracao vem de variaveis de ambiente e do arquivo `.env`, "
    "que nunca e versionado.",
    icon="🔒",
)

st.table(
    {
        "Parametro": [
            "Modo",
            "Banco de dados",
            "Nivel de log",
            "Formato de log",
            "Fuso de exibicao",
            "Capital",
            "Hash da configuracao",
        ],
        "Valor": [
            settings.mode.value,
            settings.database_url,
            settings.log_level,
            settings.log_format,
            settings.display_timezone,
            f"R$ {settings.capital:,.2f}",
            settings.config_hash(),
        ],
    }
)

st.caption(f"Modos habilitados: {', '.join(sorted(m.value for m in IMPLEMENTED_MODES))}")
st.caption("Nenhuma credencial e exibida nesta tela por principio.")

st.divider()
placeholder(
    "Fase 4",
    [
        "Perfil de risco em arquivo versionado e hasheado",
        "Configuracao do modelo multi-timeframe",
        "Pesos do score em configuracao, nunca em codigo",
    ],
)
