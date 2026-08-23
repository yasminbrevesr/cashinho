"""Tela do Scanner na linha de comando.

    python -m cashinho.core.scanner
    python -m cashinho.core.scanner --ativos PETR4,VALE3,ITUB4 --ordenar rr
    python -m cashinho.core.scanner --fonte csv --pasta dados --operaveis
    python -m cashinho.core.scanner --json > varredura.json

Nao achar oportunidade nao e' erro: o comando sai com codigo 0 e mostra
NENHUMA OPORTUNIDADE ENCONTRADA. Codigo diferente de zero fica reservado para
falha de verdade (fonte inacessivel, configuracao invalida).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ...data.csv_provider import CSVProvider
from ...data.synthetic import SyntheticProvider
from ..risk.config import RiskConfig
from ..risk.manager import RiskManager
from ..risk.state import RiskState
from .config import ORDENACOES, WATCHLIST_PADRAO, ConfiguracaoInvalidaError, ScannerConfig
from .scanner import ScannerB3
from .view import detalhe, pagina


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-scanner", description="Scanner B3 do Cashinho")

    dados = p.add_argument_group("ativos e dados")
    dados.add_argument("--ativos", default=",".join(WATCHLIST_PADRAO),
                       help="lista separada por virgula")
    dados.add_argument("--fonte", choices=["demo", "csv", "yahoo"], default="demo")
    dados.add_argument("--pasta", type=Path, default=Path("dados"))
    dados.add_argument("--dias", type=int, default=5)
    dados.add_argument("--timeframe-base", default="1m")
    dados.add_argument("--semente", type=int, default=42, help="semente da fonte demo")

    filtros = p.add_argument_group("filtros iniciais")
    filtros.add_argument("--liquidez-minima", type=float, default=5_000_000.0,
                         help="R$ negociados por pregao")
    filtros.add_argument("--volume-minimo", type=float, default=0.5,
                         help="volume recente sobre a media do ativo")
    filtros.add_argument("--atr-min", type=float, default=0.15, help="%% do preco")
    filtros.add_argument("--atr-max", type=float, default=3.0, help="%% do preco")
    filtros.add_argument("--spread-max", type=float, default=3.0, help="em ticks")

    risco = p.add_argument_group("risco")
    risco.add_argument("--capital", type=float, default=100_000.0)
    risco.add_argument("--risco-trade", type=float, default=1.0, help="%% do capital")

    saida = p.add_argument_group("saida")
    saida.add_argument("--ordenar", choices=list(ORDENACOES), default="score")
    saida.add_argument("--limite", type=int, help="quantas linhas mostrar")
    saida.add_argument("--operaveis", action="store_true",
                       help="so o que esta liberado ou aguardando gatilho")
    saida.add_argument("--detalhe", metavar="ATIVO", help="mostra a trilha completa de um ativo")
    saida.add_argument("--json", action="store_true")
    saida.add_argument("--sem-cor", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        config = ScannerConfig(
            watchlist=tuple(a.strip() for a in args.ativos.split(",") if a.strip()),
            timeframe_base=args.timeframe_base,
            dias=args.dias,
            liquidez_minima_diaria=args.liquidez_minima,
            volume_relativo_minimo=args.volume_minimo,
            atr_min_pct=args.atr_min,
            atr_max_pct=args.atr_max,
            spread_maximo_ticks=args.spread_max,
            ordenar_por=args.ordenar,
            apenas_operaveis=args.operaveis,
            max_resultados=args.limite,
        )
    except ConfiguracaoInvalidaError as e:
        print(f"configuracao invalida: {e}")
        return 2

    if args.fonte == "demo":
        provider = SyntheticProvider(semente=args.semente)
    elif args.fonte == "csv":
        try:
            provider = CSVProvider(args.pasta)
        except DataError as e:
            print(f"nao foi possivel usar a pasta de CSVs: {e}")
            return 2
    else:
        from ...data.yahoo import YahooProvider

        provider = YahooProvider()

    risco = RiskManager(
        RiskConfig(capital=args.capital, risco_por_trade_pct=args.risco_trade),
        RiskState(capital_inicial=args.capital),
    )
    resultado = ScannerB3(provider, config, risco=risco).varrer()

    if args.json:
        print(json.dumps(resultado.para_dict(), indent=2, ensure_ascii=False))
        return 0

    cores = not args.sem_cor and sys.stdout.isatty()
    if args.detalhe:
        alvo = args.detalhe.strip().upper()
        linha = next((l for l in resultado.linhas if l.symbol == alvo), None)
        if linha is None:
            print(f"{alvo} nao esta na watchlist desta varredura")
            return 2
        print(detalhe(linha, cores))
        return 0

    print(pagina(resultado, args.ordenar, cores, args.limite))
    if args.fonte == "demo":
        print("\n  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.")
    # nao achar oportunidade e' resultado, nao erro
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
