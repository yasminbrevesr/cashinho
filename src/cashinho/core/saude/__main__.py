"""Tela do System Health.

    python -m cashinho.core.saude
    python -m cashinho.core.saude --fonte yahoo --ativo PETR4
    python -m cashinho.core.saude --diario diario.jsonl --eventos eventos.json
    python -m cashinho.core.saude --json

A verificacao e' de verdade: o Market Data e' medido baixando a serie e
cronometrando; o Database, olhando o arquivo; o News, carregando a agenda.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ...models import BRT
from ..broker import PaperBroker
from ..broker.paper import ConfigPaper
from ..risk import RiskConfig, RiskManager
from .estados import Modo
from .monitor import ConfigSaude, MonitorDeSaude
from .sondas import LimiaresSaude, SondaBanco, SondaPorTelemetria
from .telemetria import Telemetria
from .view import pagina


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-saude",
                                description="Painel de saude do Cashinho")
    p.add_argument("--fonte", choices=["demo", "yahoo", "csv", "nenhuma"], default="demo")
    p.add_argument("--ativo", default="PETR4")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--pasta", type=Path, default=Path("dados"))
    p.add_argument("--diario", type=Path, help="arquivo JSONL do diario de trades")
    p.add_argument("--eventos", type=Path, help="calendario de eventos em JSON")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--modo", choices=[m.name.lower() for m in Modo], default="analise")
    p.add_argument("--atraso-offline", type=float, default=15.0,
                   help="minutos de atraso do Market Data que derrubam operacoes novas")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cor", action="store_true")
    return p


def medir_market_data(args, telemetria: Telemetria) -> None:
    """Baixa a serie de verdade e anota latencia, timestamp e erro."""
    if args.fonte == "nenhuma":
        return
    try:
        provider = _provider(args)
    except DataError as e:
        telemetria.erro("market_data", str(e))
        return

    inicio = time.monotonic()
    try:
        serie = provider.candles(args.ativo, args.timeframe, 2)
    except DataError as e:
        telemetria.erro("market_data", f"{args.fonte}: {e}")
        return
    latencia = (time.monotonic() - inicio) * 1000

    if not len(serie):
        telemetria.erro("market_data", f"{args.fonte}: serie vazia para {args.ativo}")
        return
    # o candle cobre ate o fechamento dele: e' esse o instante do dado
    from ..mtf.timeframes import parse_timeframe

    duracao = parse_timeframe(args.timeframe).duracao_minutos(375)
    fechamento = serie.candles[-1].ts + timedelta(minutes=duracao)
    telemetria.sucesso("market_data", latencia_ms=latencia,
                       dado_em=fechamento,
                       detalhe=f"{args.ativo} {args.timeframe} via {args.fonte} "
                               f"({len(serie)} candles)")


def _provider(args):
    if args.fonte == "yahoo":
        from ...data.yahoo import YahooProvider

        return YahooProvider()
    if args.fonte == "csv":
        from ...data.csv_provider import CSVProvider

        return CSVProvider(args.pasta)
    from ...data.synthetic import SyntheticProvider

    return SyntheticProvider()


def montar_monitor(args) -> MonitorDeSaude:
    telemetria = Telemetria()
    medir_market_data(args, telemetria)

    noticias = None
    if args.eventos:
        from ..noticias import AvaliadorDeEventos, FonteArquivo

        noticias = AvaliadorDeEventos(FonteArquivo(args.eventos))

    modo = Modo[args.modo.upper()]
    broker = PaperBroker(ConfigPaper(capital_inicial=args.capital))
    risco = RiskManager(RiskConfig(capital=args.capital))
    config = ConfigSaude(limiares=LimiaresSaude(market_data_offline_min=args.atraso_offline))

    monitor = MonitorDeSaude(telemetria, config, modo=modo, risco=risco,
                             broker=broker, noticias=noticias,
                             banco=args.diario if args.diario else None)
    return monitor


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    monitor = montar_monitor(args)
    saude = monitor.verificar()

    if args.json:
        print(json.dumps(saude.para_dict(), indent=2, ensure_ascii=False))
        return 0

    print(pagina(saude, cores=not args.sem_cor and sys.stdout.isatty()))
    if args.fonte == "demo":
        print("  Market Data medido com dados simulados (--fonte demo).\n")
    return 2 if saude.bloqueia_novas_operacoes else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
