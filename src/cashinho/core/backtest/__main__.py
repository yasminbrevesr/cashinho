"""Pagina Backtest na linha de comando.

    python -m cashinho.core.backtest --ativo PETR4 --dias 10 --capital 100000
    python -m cashinho.core.backtest --fonte csv --pasta dados --ativo PETR4
    python -m cashinho.core.backtest --estrategia baseline-tendencia --risco-trade 0.5 \
            --spread 2 --slippage 1 --corretagem 4.90 --taxas 0.03
    python -m cashinho.core.backtest --json > resultado.json

A fonte ``demo`` gera pregoes sinteticos reproduziveis - nao e' mercado, e'
so para exercitar o sistema sem depender de dados externos.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, time
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ...data.csv_provider import CSVProvider
from ...data.synthetic import SyntheticProvider
from ..risk.config import RiskConfig
from ..strategy.base import disponiveis, obter
from .comparacao import TIMEFRAMES_PADRAO, comparar as comparar_timeframes
from .config import BacktestConfig
from .costs import ModeloCustos
from .engine import BacktestEngine
from .view import pagina, resumo
from .view_comparacao import pagina_comparacao
from ..ui.argumentos import data as _data


def _hora(texto: str) -> Optional[time]:
    if texto.lower() in ("nao", "none", "-"):
        return None
    h, m = texto.split(":")[:2]
    return time(int(h), int(m))


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-backtest", description="Pagina Backtest do Cashinho")

    dados = p.add_argument_group("ativo, periodo e dados")
    dados.add_argument("--ativo", default="PETR4")
    dados.add_argument("--fonte", choices=["demo", "csv", "yahoo"], default="demo")
    dados.add_argument("--pasta", type=Path, default=Path("dados"), help="pasta dos CSVs")
    dados.add_argument("--dias", type=int, default=10, help="quantos pregoes buscar")
    dados.add_argument("--inicio", type=_data, help="recorte do periodo (AAAA-MM-DD)")
    dados.add_argument("--fim", type=_data)
    dados.add_argument("--timeframe", default="5m", help="timeframe da estrategia")
    dados.add_argument("--timeframe-base", default="1m", help="timeframe de execucao")

    conta = p.add_argument_group("capital e risco")
    conta.add_argument("--capital", type=float, default=100_000.0)
    conta.add_argument("--risco-trade", type=float, default=1.0, help="%% do capital por trade")
    conta.add_argument("--max-trades", type=int, default=5)
    conta.add_argument("--perda-diaria", type=float, default=3.0, help="%% do capital")

    custos = p.add_argument_group("custos")
    custos.add_argument("--spread", type=float, default=1.0, help="spread do book, em ticks")
    custos.add_argument("--slippage", type=float, default=1.0, help="derrapagem, em ticks")
    custos.add_argument("--corretagem", type=float, default=0.0, help="R$ por ordem")
    custos.add_argument("--taxas", type=float, default=0.03, help="%% de taxas da B3 por ponta")

    execucao = p.add_argument_group("execucao")
    execucao.add_argument("--estrategia", default="baseline-tendencia")
    execucao.add_argument("--entrada-ate", type=_hora, default="16:30")
    execucao.add_argument("--fechar-em", type=_hora, default="17:40")
    execucao.add_argument("--intracandle", choices=["stop", "alvo", "nenhuma"], default="stop")
    execucao.add_argument("--semente", type=int, default=42, help="semente da fonte demo")

    comparar = p.add_argument_group("comparar timeframes")
    comparar.add_argument("--comparar", action="store_true",
                          help="roda a mesma estrategia em varios timeframes e compara")
    comparar.add_argument("--timeframes", default=",".join(TIMEFRAMES_PADRAO),
                          help="lista separada por virgula (padrao: 1m,5m,15m,30m,60m,1d)")

    saida = p.add_argument_group("saida")
    saida.add_argument("--trades", type=int, default=20, help="quantos trades listar")
    saida.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    saida.add_argument("--resumo", action="store_true", help="uma linha so")
    saida.add_argument("--sem-cor", action="store_true")
    return p


def carregar_serie(args):
    if args.fonte == "demo":
        return SyntheticProvider(semente=args.semente).candles(args.ativo, args.timeframe_base, args.dias)
    if args.fonte == "csv":
        return CSVProvider(args.pasta).candles(args.ativo, args.timeframe_base, args.dias)
    from ...data.yahoo import YahooProvider

    return YahooProvider().candles(args.ativo, args.timeframe_base, args.dias)


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        estrategia = obter(args.estrategia)
    except KeyError:
        print(f"estrategia desconhecida. Disponiveis: {', '.join(disponiveis())}")
        return 2

    try:
        serie = carregar_serie(args)
    except DataError as e:
        print(f"nao foi possivel carregar os dados: {e}")
        return 2

    config = BacktestConfig(
        symbol=args.ativo.upper(),
        timeframe_base=args.timeframe_base,
        timeframe_setup=args.timeframe,
        inicio=args.inicio,
        fim=args.fim,
        capital_inicial=args.capital,
        risco=RiskConfig(
            capital=args.capital,
            risco_por_trade_pct=args.risco_trade,
            max_trades_dia=args.max_trades,
            perda_max_diaria_pct=args.perda_diaria,
        ),
        custos=ModeloCustos(
            spread_ticks=args.spread,
            slippage_ticks=args.slippage,
            corretagem_fixa=args.corretagem,
            taxas_b3_pct=args.taxas,
        ),
        entrada_ate=args.entrada_ate,
        fechar_em=args.fechar_em,
        prioridade_intracandle=args.intracandle,
    )

    if args.comparar:
        timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
        comparacao = comparar_timeframes(
            lambda: obter(args.estrategia), serie, config, timeframes
        )
        if args.json:
            print(json.dumps(comparacao.para_dict(), indent=2, ensure_ascii=False))
        else:
            cores = not args.sem_cor and sys.stdout.isatty()
            print(pagina_comparacao(comparacao, cores=cores))
            if args.fonte == "demo":
                print("\n  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.")
        return 0

    resultado = BacktestEngine(estrategia, config).rodar(serie)

    if args.json:
        print(json.dumps(resultado.para_dict(), indent=2, ensure_ascii=False))
    elif args.resumo:
        print(resumo(resultado))
    else:
        cores = not args.sem_cor and sys.stdout.isatty()
        print(pagina(resultado, cores=cores, limite_trades=args.trades))
        if args.fonte == "demo":
            print("\n  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
