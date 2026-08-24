"""Market Replay na linha de comando.

    python -m cashinho.core.replay --ativo PETR4 --velocidade maxima
    python -m cashinho.core.replay --data 2026-08-20 --velocidade 10x --acompanhar 60
    python -m cashinho.core.replay --listar-dias
    python -m cashinho.core.replay --json

``--velocidade`` aceita 1x, 5x, 10x, 60x e maxima. Em 1x o replay espera o
tempo real entre candles; em maxima, roda sem pausa.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ...data.csv_provider import CSVProvider
from ...data.synthetic import SyntheticProvider
from .fita import dias_disponiveis
from .replay import MarketReplay, PassoReplay, ReplayConfig
from .velocidade import Relogio, Velocidade
from .view import pagina, resumo
from ..ui.argumentos import data as _data


def _velocidade(texto: str) -> Velocidade:
    try:
        return Velocidade.de_texto(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-replay", description="Market Replay do Cashinho")

    escolha = p.add_argument_group("o que reproduzir")
    escolha.add_argument("--ativo", default="PETR4")
    escolha.add_argument("--data", type=_data, dest="dia", help="pregao a reproduzir")
    escolha.add_argument("--timeframe", default="1m", help="timeframe dos candles")
    escolha.add_argument("--velocidade", type=_velocidade, default=Velocidade.MAXIMA,
                         help="1x, 5x, 10x, 60x ou maxima")

    fonte = p.add_argument_group("dados")
    fonte.add_argument("--fonte", choices=["demo", "csv", "yahoo"], default="demo")
    fonte.add_argument("--pasta", type=Path, default=Path("dados"))
    fonte.add_argument("--dias", type=int, default=5)
    fonte.add_argument("--semente", type=int, default=3)

    conta = p.add_argument_group("conta")
    conta.add_argument("--capital", type=float, default=100_000.0)
    conta.add_argument("--risco-trade", type=float, default=1.0, help="%% do capital")

    saida = p.add_argument_group("saida")
    saida.add_argument("--passos", type=int, help="para depois de N candles")
    saida.add_argument("--acompanhar", type=int, metavar="N",
                       help="redesenha a tela a cada N candles")
    saida.add_argument("--listar-dias", action="store_true",
                       help="mostra os pregoes disponiveis e sai")
    saida.add_argument("--json", action="store_true")
    saida.add_argument("--sem-cor", action="store_true")
    return p


def carregar_serie(args):
    if args.fonte == "demo":
        return SyntheticProvider(semente=args.semente).candles(
            args.ativo, args.timeframe, args.dias)
    if args.fonte == "csv":
        return CSVProvider(args.pasta).candles(args.ativo, args.timeframe, args.dias)
    from ...data.yahoo import YahooProvider

    return YahooProvider().candles(args.ativo, args.timeframe, args.dias)


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        serie = carregar_serie(args)
    except DataError as e:
        print(f"nao foi possivel carregar os dados: {e}")
        return 2

    dias = dias_disponiveis(serie)
    if args.listar_dias:
        print(f"pregoes disponiveis para {args.ativo.upper()} ({args.timeframe}):")
        for d in dias:
            candles = sum(1 for c in serie.candles if c.ts.date() == d)
            print(f"  {d:%d/%m/%Y}  {candles} candles")
        return 0

    dia = args.dia or (dias[-1] if dias else None)
    if dia is not None and dia not in dias:
        print(f"nao ha candles de {args.ativo.upper()} em {dia:%d/%m/%Y}")
        print(f"disponiveis: {', '.join(d.isoformat() for d in dias)}")
        return 2

    config = ReplayConfig(
        symbol=args.ativo.upper(), dia=dia, timeframe_base=args.timeframe,
        velocidade=args.velocidade, capital=args.capital,
        risco_por_trade_pct=args.risco_trade,
    )
    cores = not args.sem_cor and sys.stdout.isatty()
    replay = MarketReplay(serie, config, relogio=Relogio(args.velocidade))

    if args.acompanhar and not args.json:
        def ao_passo(passo: PassoReplay) -> None:
            if passo.indice % args.acompanhar == 0 or passo.eventos:
                print(pagina(replay, cores))
                print()
        replay.executar(ate=args.passos, aoPasso=ao_passo)
    else:
        replay.executar(ate=args.passos)

    if args.json:
        print(json.dumps({
            "replay": replay.estado.para_dict(),
            "conta": replay.saldo.para_dict(),
            "diario": [r.para_dict() for r in replay.diario],
        }, indent=2, ensure_ascii=False))
        return 0

    print(pagina(replay, cores))
    print()
    print(f"  {resumo(replay)}")
    if args.fonte == "demo":
        print("  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
