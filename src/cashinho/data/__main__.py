"""Tela ANALISE de market data.

    python -m cashinho.data --ativo PETR4
    python -m cashinho.data --ativo PETR4 --provider brapi --timeframe 1d
    python -m cashinho.data --providers
    python -m cashinho.data --ativo PETR4 --finalidade scanner_intradiario
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from ..core.ui import c
from ..settings import carregar
from .base import DataError
from .fabrica import catalogo, construir, montar_servico
from .servico import Finalidade, MarketDataService
from .status import CapacidadeAusenteError
from .view import pagina_analise, secao_providers


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-dados",
                                description="Market Data do Cashinho")
    p.add_argument("--ativo", default="PETR4")
    p.add_argument("--timeframe", default="1d")
    p.add_argument("--dias", type=int, default=30)
    p.add_argument("--provider", default="", help="forca o provedor historico")
    p.add_argument("--finalidade", default="historico",
                   choices=[f.value for f in Finalidade])
    p.add_argument("--cotacao", action="store_true", help="tambem busca a cotacao")
    p.add_argument("--providers", action="store_true", help="lista os provedores")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cor", action="store_true")
    return p


def listar(args) -> int:
    cfg = carregar()
    if args.json:
        print(json.dumps({"catalogo": catalogo(), "configuracao": cfg.para_dict()},
                         indent=2, ensure_ascii=False))
        return 0
    print()
    print(f"  {'PROVIDER':<14}{'DISPONIVEL':<13}DESCRICAO")
    for nome, info in catalogo().items():
        marca = "sim" if info["disponivel"] else "ainda nao"
        print(f"  {nome:<14}{marca:<13}{info['descricao']}")
    print()
    print(f"  configurado como historico : {cfg.historico}")
    print(f"  configurado como tempo real: {cfg.tempo_real or 'NAO CONFIGURADO'}")
    print()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.providers:
        return listar(args)

    cores = not args.sem_cor and sys.stdout.isatty()
    cfg = carregar()
    finalidade = Finalidade(args.finalidade)

    try:
        if args.provider:
            servico = MarketDataService(historico=construir(args.provider, cfg))
        else:
            servico = montar_servico(cfg)
        leitura = servico.candles(args.ativo, args.timeframe, args.dias, finalidade)
    except (DataError, CapacidadeAusenteError) as e:
        print(f"\n  {c('NAO FOI POSSIVEL CARREGAR', 'vermelho', 'negrito', ativo=cores)}")
        print(f"  {e}\n")
        return 2

    cotacao = None
    if args.cotacao:
        try:
            cotacao = servico.cotacao(args.ativo, finalidade)
        except (DataError, CapacidadeAusenteError, NotImplementedError) as e:
            print(f"  cotacao indisponivel: {e}")

    if args.json:
        payload = leitura.para_dict()
        if cotacao is not None:
            payload["cotacao"] = cotacao.para_dict()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(pagina_analise(leitura, cotacao, cores))
    print(secao_providers(servico, cores))
    print()
    return 0 if leitura.utilizavel else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
