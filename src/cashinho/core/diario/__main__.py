"""Pagina Diario na linha de comando.

    python -m cashinho.core.diario
    python -m cashinho.core.diario --ativo PETR4 --resultado perdedor
    python -m cashinho.core.diario --setup pullback --de 2026-08-01 --ate 2026-08-31
    python -m cashinho.core.diario --grupos setup,horario --limite 10
    python -m cashinho.core.diario --detalhe reg-abc123

O arquivo padrao e' ``~/.cashinho/diario.jsonl``, o mesmo que o Paper Trading
alimenta sozinho.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from ...models import Direction
from .diario import DiarioDeTrades
from .estatisticas import AGRUPAMENTOS
from .modelos import Filtro
from .view import detalhe_registro, pagina

ARQUIVO_PADRAO = Path.home() / ".cashinho" / "diario.jsonl"


def _data(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"data invalida: {texto!r} (use AAAA-MM-DD)") from e


def _direcao(texto: str) -> Direction:
    t = texto.strip().lower()
    if t in ("compra", "long", "c"):
        return Direction.LONG
    if t in ("venda", "short", "v"):
        return Direction.SHORT
    raise argparse.ArgumentTypeError(f"direcao invalida: {texto!r} (use compra ou venda)")


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-diario", description="Diario de Trades do Cashinho")
    p.add_argument("--arquivo", type=Path, default=ARQUIVO_PADRAO)

    f = p.add_argument_group("filtros")
    f.add_argument("--ativo")
    f.add_argument("--setup", help="trecho do nome do setup")
    f.add_argument("--timeframe")
    f.add_argument("--de", type=_data, dest="inicio")
    f.add_argument("--ate", type=_data, dest="fim")
    f.add_argument("--resultado", choices=["vencedor", "perdedor", "zerado"])
    f.add_argument("--direcao", type=_direcao)

    s = p.add_argument_group("saida")
    s.add_argument("--grupos", default=",".join(AGRUPAMENTOS),
                   help=f"agrupamentos a mostrar ({', '.join(AGRUPAMENTOS)})")
    s.add_argument("--limite", type=int, default=30, help="quantas operacoes listar")
    s.add_argument("--detalhe", metavar="ID", help="mostra uma operacao inteira")
    s.add_argument("--json", action="store_true")
    s.add_argument("--sem-cor", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    diario = DiarioDeTrades.carregar(args.arquivo)

    filtro = Filtro(
        ativo=args.ativo, setup=args.setup, timeframe=args.timeframe,
        inicio=args.inicio, fim=args.fim, resultado=args.resultado, direcao=args.direcao,
    )

    if args.detalhe:
        alvo = args.detalhe.strip()
        registro = next((r for r in diario if r.id == alvo), None)
        if registro is None:
            print(f"operacao {alvo} nao encontrada no diario")
            return 2
        cores = not args.sem_cor and sys.stdout.isatty()
        print(detalhe_registro(registro, cores))
        return 0

    if args.json:
        print(json.dumps(diario.para_dict(filtro), indent=2, ensure_ascii=False))
        return 0

    grupos = [g.strip() for g in args.grupos.split(",") if g.strip() in AGRUPAMENTOS]
    cores = not args.sem_cor and sys.stdout.isatty()
    print(pagina(diario, filtro, cores, args.limite, grupos))
    if len(diario) == 0:
        print(f"\n  o diario esta vazio ({args.arquivo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
