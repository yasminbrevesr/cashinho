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
    p.add_argument("--acompanhar", type=float, metavar="SEGUNDOS",
                   help="redesenha a tela a cada N segundos (Ctrl+C para sair)")
    p.add_argument("--vezes", type=int, help="quantas atualizacoes antes de parar")
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


def main(argv: Optional[list[str]] = None, dormir=None) -> int:
    args = construir_parser().parse_args(argv)
    if args.providers:
        return listar(args)

    if args.acompanhar and not args.json:
        return acompanhar(args, dormir)

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


def acompanhar(args, dormir=None) -> int:
    """Redesenha a tela em intervalo fixo.

    Um laco com intervalo, aqui, e' o certo: isto e' um programa de terminal,
    nao uma pagina. O intervalo minimo e' de um segundo - o objetivo e' ver o
    dado novo chegar, nao fazer alta frequencia.
    """
    import time

    espera = max(float(args.acompanhar), 1.0)
    esperar = dormir or time.sleep
    restantes = args.vezes if args.vezes else None
    codigo = 0

    try:
        while restantes is None or restantes > 0:
            print("\033[2J\033[H", end="")   # limpa a tela
            codigo = _uma_leitura(args)
            if restantes is not None:
                restantes -= 1
                if restantes <= 0:
                    break
            print(f"  atualizando a cada {espera:.0f}s - Ctrl+C para sair")
            esperar(espera)
    except KeyboardInterrupt:
        print("\n  acompanhamento encerrado")
    return codigo


def _uma_leitura(args) -> int:
    """Uma passada da tela - o mesmo caminho do modo sem acompanhamento."""
    return main([*_argumentos_base(args)])


def _argumentos_base(args) -> list[str]:
    base = ["--ativo", args.ativo, "--timeframe", args.timeframe,
            "--dias", str(args.dias), "--finalidade", args.finalidade]
    if args.provider:
        base += ["--provider", args.provider]
    if args.cotacao:
        base += ["--cotacao"]
    if args.sem_cor:
        base += ["--sem-cor"]
    return base


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
