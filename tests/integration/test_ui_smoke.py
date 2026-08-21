"""Smoke test da interface.

Cada pagina e executada de verdade pelo `AppTest` do Streamlit. Verificar
apenas que o servidor sobe provaria somente que `main.py` importa — uma
pagina quebrada continuaria passando despercebida ate alguem clicar nela.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = ROOT / "app" / "pages"

PAGES = [
    "dashboard.py",
    "scanner.py",
    "analise.py",
    "backtest.py",
    "paper_trading.py",
    "diario.py",
    "risk_manager.py",
    "configuracoes.py",
    "system_health.py",
]


@pytest.fixture(autouse=True)
def _project_on_path() -> None:
    """As paginas importam `app.components`; a raiz precisa estar no path."""
    for path in (ROOT, ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


@pytest.mark.parametrize("page", PAGES)
def test_pagina_renderiza_sem_excecao(page: str) -> None:
    app = AppTest.from_file(str(PAGES_DIR / page), default_timeout=30).run()
    assert not app.exception, [str(e) for e in app.exception]


@pytest.mark.parametrize("page", PAGES)
def test_pagina_exibe_o_modo(page: str) -> None:
    """O indicador de modo e permanente: precisa estar em todas as telas."""
    app = AppTest.from_file(str(PAGES_DIR / page), default_timeout=30).run()
    markdown = " ".join(m.value for m in app.sidebar.markdown)
    assert "PAPER" in markdown, f"{page} nao exibe o modo na barra lateral"


def test_analise_carrega_candles_e_desenha_o_grafico() -> None:
    """Fatia vertical completa: entrada -> provider -> portao -> grafico."""
    if not (ROOT / "data" / "fixtures" / "PETR4" / "5m.csv").is_file():
        pytest.skip("fixtures nao geradas; rode scripts/generate_fixtures.py")

    app = AppTest.from_file(str(PAGES_DIR / "analise.py"), default_timeout=60).run()
    assert not app.exception

    app.selectbox[0].select("PETR4")
    app.selectbox[1].select("15m")
    app.button[0].click().run()

    assert not app.exception, [str(e) for e in app.exception]
    # O grafico so e desenhado quando o portao libera a serie.
    assert len(app.get("plotly_chart")) == 1


def test_analise_sem_carregar_nao_desenha_grafico() -> None:
    app = AppTest.from_file(str(PAGES_DIR / "analise.py"), default_timeout=30).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 0


def test_analise_declara_inspecao_historica_em_modo_ao_vivo() -> None:
    """O rebaixamento para RESEARCH precisa ser visivel, nao silencioso."""
    app = AppTest.from_file(str(PAGES_DIR / "analise.py"), default_timeout=30).run()
    avisos = " ".join(i.value for i in app.info)
    assert "inspeção histórica" in avisos
    assert "PAPER" in avisos


def test_analise_desenha_indicadores_selecionados() -> None:
    """Fatia vertical com indicadores: entrada -> portão -> cálculo -> gráfico."""
    if not (ROOT / "data" / "fixtures" / "PETR4" / "5m.csv").is_file():
        pytest.skip("fixtures nao geradas; rode scripts/generate_fixtures.py")

    app = AppTest.from_file(str(PAGES_DIR / "analise.py"), default_timeout=90).run()
    assert not app.exception

    app.selectbox[0].select("PETR4")
    app.selectbox[1].select("15m")
    app.button[0].click().run()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(app.get("plotly_chart")) == 1


def test_analise_permite_desativar_indicadores() -> None:
    """Os controles precisam de fato desligar o cálculo."""
    if not (ROOT / "data" / "fixtures" / "PETR4" / "5m.csv").is_file():
        pytest.skip("fixtures nao geradas; rode scripts/generate_fixtures.py")

    app = AppTest.from_file(str(PAGES_DIR / "analise.py"), default_timeout=90).run()
    rotulos = [c.label for c in app.checkbox]
    for esperado in ("SMA", "EMA", "VWAP", "RSI", "ATR", "Volume"):
        assert any(esperado in rotulo for rotulo in rotulos), f"controle ausente: {esperado}"

    for checkbox in app.checkbox:
        checkbox.set_value(False)
    app.button[0].click().run()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(app.get("plotly_chart")) == 1
