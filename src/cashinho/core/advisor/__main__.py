"""Tela do Timeframe Advisor.

    python -m cashinho.core.advisor --ativo PETR4
    python -m cashinho.core.advisor --fonte csv --pasta dados --dias 10
    python -m cashinho.core.advisor --card          # so o card do dashboard
    python -m cashinho.core.advisor --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ..ui.argumentos import instante as _instante
from .advisor import ConfigAdvisor, TimeframeAdvisor
from .estabilidade import ConfigEstabilidade, RecomendacaoAtual
from .score import PesosAdvisor
from .view import card, pagina


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in texto.split(",") if t.strip())


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cashinho-advisor",
        description="Timeframe Advisor: em qual granularidade operar agora")
    dados = p.add_argument_group("dados")
    dados.add_argument("--ativo", default="PETR4")
    dados.add_argument("--fonte", choices=["demo", "csv", "yahoo", "metatrader"],
                       default="demo")
    dados.add_argument("--pasta", type=Path, default=Path("dados"))
    dados.add_argument("--dias", type=int, default=10)
    dados.add_argument("--semente", type=int, default=3)
    dados.add_argument("--instante", type=_instante,
                       help="avalia como se fosse este momento (AAAA-MM-DDTHH:MM)")

    ajustes = p.add_argument_group("ajustes")
    ajustes.add_argument("--setup", type=_lista,
                         help="candidatos a setup (padrao: 1m,2m,3m,5m,10m,15m)")
    ajustes.add_argument("--contexto", type=_lista,
                         help="candidatos a contexto (padrao: 15m,30m,60m)")
    ajustes.add_argument("--atual", help="timeframe ja recomendado (liga a histerese)")
    ajustes.add_argument("--atual-ha", type=float, default=60.0,
                         help="ha quantos minutos ele foi recomendado")
    ajustes.add_argument("--confianca-minima", type=float, default=15.0)

    saida = p.add_argument_group("saida")
    saida.add_argument("--card", action="store_true", help="so o card do dashboard")
    saida.add_argument("--json", action="store_true")
    saida.add_argument("--sem-cor", action="store_true")
    return p


def carregar_serie(args):
    """A serie de 1m - de qualquer provider. O Advisor nao sabe qual."""
    from ...data.fabrica import construir

    extra = {}
    if args.fonte == "demo":
        extra["semente"] = args.semente
    elif args.fonte == "csv":
        extra["pasta"] = args.pasta
    provider = construir(args.fonte, **extra)
    return provider.candles(args.ativo, "1m", args.dias)


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        serie = carregar_serie(args)
    except DataError as e:
        print(f"\n  nao foi possivel carregar {args.ativo}: {e}\n")
        return 2

    config = ConfigAdvisor(
        setup=args.setup or ConfigAdvisor().setup,
        contexto=args.contexto or ConfigAdvisor().contexto,
        confianca_minima=args.confianca_minima,
    )

    atual = None
    if args.atual:
        from datetime import timedelta

        instante = args.instante or serie.candles[-1].ts
        atual = RecomendacaoAtual(args.atual,
                                  instante - timedelta(minutes=args.atual_ha), 0.0)

    rec = TimeframeAdvisor(config).avaliar(serie, as_of=args.instante, atual=atual)

    if args.json:
        print(json.dumps(rec.para_dict(), indent=2, ensure_ascii=False))
        return 0

    cores = not args.sem_cor and sys.stdout.isatty()
    print("\n" + (card(rec, cores) if args.card else pagina(rec, cores)))
    if args.fonte == "demo":
        print("  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.\n")
    return 0 if rec.tem_recomendacao else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
