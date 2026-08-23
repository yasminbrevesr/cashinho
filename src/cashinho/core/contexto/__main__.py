"""Tela do contexto de mercado.

    python -m cashinho.core.contexto
    python -m cashinho.core.contexto --fonte real
    python -m cashinho.core.contexto --instrumentos ibovespa,dolar,sp500
    python -m cashinho.core.contexto --listar-instrumentos
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .fontes import FonteComposta, FonteDeContexto, FonteBCB, fonte_demo, fonte_yahoo
from .instrumentos import CATALOGO, POR_CHAVE
from .motor import ConfigContexto, MotorDeContexto
from .view import pagina


def _instrumentos(texto: str) -> tuple[str, ...]:
    chaves = tuple(p.strip().lower() for p in texto.split(",") if p.strip())
    desconhecidos = [c for c in chaves if c not in POR_CHAVE]
    if desconhecidos:
        raise argparse.ArgumentTypeError(
            f"instrumento desconhecido: {', '.join(desconhecidos)} "
            f"(conhecidos: {', '.join(sorted(POR_CHAVE))})"
        )
    if not chaves:
        raise argparse.ArgumentTypeError("informe ao menos um instrumento")
    return chaves


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cashinho-contexto",
        description="Contexto de mercado do Cashinho (Ibovespa, dolar, juros, commodities, "
                    "indices internacionais)",
    )
    p.add_argument("--fonte", choices=["demo", "real"], default="demo",
                   help="demo = dados simulados (padrao); real = Yahoo + Banco Central")
    p.add_argument("--instrumentos", type=_instrumentos,
                   default=tuple(i.chave for i in CATALOGO))
    p.add_argument("--timeframe", default="60m")
    p.add_argument("--dias", type=int, default=30)
    p.add_argument("--limiar-correlacao", type=float, default=0.4)
    p.add_argument("--semente", type=int, default=7, help="so vale para --fonte demo")
    p.add_argument("--listar-instrumentos", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cor", action="store_true")
    return p


def montar_fonte(args) -> FonteDeContexto:
    if args.fonte == "demo":
        return fonte_demo(semente=args.semente)
    # cada fonte cobre o que ela realmente cobre: o Yahoo nao tem juros do
    # Brasil, e o Banco Central nao tem indice nem commodity
    return FonteComposta([fonte_yahoo(), FonteBCB()])


def listar(args) -> int:
    if args.json:
        print(json.dumps([i.para_dict() for i in CATALOGO], indent=2, ensure_ascii=False))
        return 0
    print()
    print(f"  {'INSTRUMENTO':<24}{'PAPEL':<24}FONTE")
    for i in CATALOGO:
        fontes = ", ".join(sorted(i.tickers)) or "FONTE A CONFIRMAR"
        print(f"  {i.nome:<24}{i.papel.rotulo:<24}{fontes}")
        if i.observacao:
            print(f"  {'':<24}{'':<24}{i.observacao}")
    print()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.listar_instrumentos:
        return listar(args)

    config = ConfigContexto(
        instrumentos=tuple(args.instrumentos),
        timeframe=args.timeframe,
        dias=args.dias,
        limiar_correlacao=args.limiar_correlacao,
    )
    contexto = MotorDeContexto(montar_fonte(args), config).montar()

    if args.json:
        print(json.dumps(contexto.para_dict(), indent=2, ensure_ascii=False))
    else:
        print(pagina(contexto, cores=not args.sem_cor and sys.stdout.isatty()))
        if args.fonte == "demo":
            print("  fonte: dados simulados (--fonte demo). Nao sao precos reais.\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
