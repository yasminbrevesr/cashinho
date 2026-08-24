"""Le o log de um pregao.

    python -m cashinho.core.log
    python -m cashinho.core.log --dia 2026-08-21 --nivel aviso
    python -m cashinho.core.log --componente market_data --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from ..ui.argumentos import data as _data
from .niveis import Nivel, nivel_de
from .registrador import PASTA_PADRAO, ler
from .view import pagina


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-log",
                                description="Log estruturado do Cashinho")
    p.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    p.add_argument("--prefixo", default="cashinho")
    p.add_argument("--dia", type=_data, help="AAAA-MM-DD (padrao: hoje)")
    p.add_argument("--nivel", type=nivel_de, default=Nivel.DEBUG,
                   help="mostra deste nivel para cima")
    p.add_argument("--componente", default="")
    p.add_argument("--limite", type=int, default=40)
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cor", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    dia = args.dia or date.today()
    arquivo = args.pasta / f"{args.prefixo}-{dia.isoformat()}.jsonl"

    if not arquivo.exists():
        print(f"\n  sem log para {dia.isoformat()}: {arquivo} nao existe")
        print("  (o log so grava quando um Registrador e' configurado com --pasta)\n")
        return 1

    eventos, descartadas = ler(arquivo)
    eventos = tuple(
        e for e in eventos
        if e.nivel.peso >= args.nivel.peso
        and (not args.componente or e.componente == args.componente)
    )
    eventos = tuple(reversed(eventos))  # o mais novo primeiro

    if args.json:
        print(json.dumps({
            "arquivo": str(arquivo),
            "eventos": [e.para_dict() for e in eventos],
            "descartadas": list(descartadas),
        }, indent=2, ensure_ascii=False))
        return 0

    print(pagina(eventos, limite=args.limite,
                 cores=not args.sem_cor and sys.stdout.isatty(),
                 descartadas=descartadas))
    if not eventos and descartadas:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
