"""Pipeline de carga: provider + capacidade + portao de qualidade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cashinho.adapters.providers.csv_provider import CsvHistoricalProvider
from cashinho.core.time.clocks import FrozenClock
from cashinho.domain.enums import DataStatus, Mode, Timeframe
from cashinho.pipeline.market_data import load_market_data
from tests.conftest import REFERENCE_INSTANT

pytestmark = pytest.mark.integration

HEADER = "timestamp,open,high,low,close,volume\n"
BASE = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


@pytest.fixture
def provider(tmp_path: Path) -> CsvHistoricalProvider:
    linhas = []
    for i in range(40):
        moment = BASE + timedelta(minutes=5 * i)
        price = 10 + i * 0.05
        linhas.append(
            f"{moment.isoformat()},{price:.2f},{price + 0.2:.2f},"
            f"{price - 0.2:.2f},{price + 0.05:.2f},{5000 + i}"
        )
    path = tmp_path / "PETR4" / "5m.csv"
    path.parent.mkdir(parents=True)
    path.write_text(HEADER + "\n".join(linhas) + "\n", encoding="utf-8")
    return CsvHistoricalProvider(tmp_path, FrozenClock(REFERENCE_INSTANT), name="csv-teste")


def _load(provider: CsvHistoricalProvider, *, mode: Mode, clock: FrozenClock, **kwargs: object):
    return load_market_data(
        provider,
        symbol="PETR4",
        timeframe=Timeframe.M5,
        start=BASE,
        end=BASE + timedelta(days=1),
        clock=clock,
        mode=mode,
        **kwargs,  # type: ignore[arg-type]
    )


def test_carga_completa_em_research(provider: CsvHistoricalProvider) -> None:
    clock = FrozenClock(BASE + timedelta(hours=4))
    result = _load(provider, mode=Mode.RESEARCH, clock=clock)
    assert result.report.status is DataStatus.OK
    assert not result.blocked
    assert result.usable_series is not None
    assert len(result.usable_series) == 40
    assert result.provider == "csv-teste"


def test_provider_historico_nao_serve_a_paper(provider: CsvHistoricalProvider) -> None:
    """D9 na pratica: fonte sem tempo real nao habilita modo ao vivo."""
    clock = FrozenClock(BASE + timedelta(hours=4))
    result = _load(provider, mode=Mode.PAPER, clock=clock)
    assert result.blocked
    assert result.rejection_reason is not None
    assert "tempo real" in result.rejection_reason
    assert result.usable_series is None


def test_bloqueio_por_capacidade_nao_consulta_a_fonte(tmp_path: Path) -> None:
    """Sem arquivo algum, PAPER ainda e recusado — a checagem vem antes da carga."""
    vazio = CsvHistoricalProvider(tmp_path, FrozenClock(REFERENCE_INSTANT))
    result = load_market_data(
        vazio,
        symbol="PETR4",
        timeframe=Timeframe.M5,
        start=BASE,
        end=BASE + timedelta(days=1),
        clock=FrozenClock(REFERENCE_INSTANT),
        mode=Mode.PAPER,
    )
    assert result.blocked
    assert result.rejection_reason is not None


def test_periodo_sem_dados_bloqueia(provider: CsvHistoricalProvider) -> None:
    clock = FrozenClock(BASE + timedelta(days=200))
    result = load_market_data(
        provider,
        symbol="PETR4",
        timeframe=Timeframe.M5,
        start=BASE + timedelta(days=100),
        end=BASE + timedelta(days=101),
        clock=clock,
        mode=Mode.RESEARCH,
    )
    assert result.blocked
    assert any(i.code == "EMPTY" for i in result.report.issues)
    assert result.usable_series is None


def test_amostra_curta_bloqueia(provider: CsvHistoricalProvider) -> None:
    clock = FrozenClock(BASE + timedelta(hours=4))
    result = load_market_data(
        provider,
        symbol="PETR4",
        timeframe=Timeframe.M5,
        start=BASE,
        end=BASE + timedelta(minutes=25),
        clock=clock,
        mode=Mode.RESEARCH,
        minimum_candles=20,
    )
    assert result.blocked
    assert any(i.code == "INSUFFICIENT" for i in result.report.issues)


def test_serie_bloqueada_preserva_a_evidencia(provider: CsvHistoricalProvider) -> None:
    """A tela precisa explicar o bloqueio; retorno vazio esconderia o motivo."""
    clock = FrozenClock(BASE + timedelta(hours=4))
    result = _load(provider, mode=Mode.PAPER, clock=clock)
    assert result.report is not None
    assert result.series is not None


def test_resultado_registra_o_modo(provider: CsvHistoricalProvider) -> None:
    clock = FrozenClock(BASE + timedelta(hours=4))
    assert _load(provider, mode=Mode.BACKTEST, clock=clock).mode is Mode.BACKTEST


def test_fixtures_do_repositorio_passam_no_portao() -> None:
    """Regressao sobre as fixtures reais geradas pelo script.

    Se a geracao produzir serie incoerente, o portao deve reprovar aqui e
    nao na interface.
    """
    root = Path(__file__).resolve().parents[2] / "data" / "fixtures"
    if not (root / "PETR4" / "15m.csv").is_file():
        pytest.skip("fixtures nao geradas; rode scripts/generate_fixtures.py")

    clock = FrozenClock(datetime(2026, 8, 20, 12, 0, tzinfo=UTC))
    provider = CsvHistoricalProvider(root, clock, name="csv-fixtures")
    result = load_market_data(
        provider,
        symbol="PETR4",
        timeframe=Timeframe.M15,
        start=datetime(2026, 7, 20, tzinfo=UTC),
        end=datetime(2026, 8, 20, tzinfo=UTC),
        clock=clock,
        mode=Mode.RESEARCH,
    )
    assert not result.blocked, [str(i) for i in result.report.issues]
    assert result.usable_series is not None
    assert len(result.usable_series) > 100
