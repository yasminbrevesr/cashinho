"""Pagina Risk Manager na linha de comando.

    python -m cashinho.core.risk                      # mostra a pagina
    python -m cashinho.core.risk configurar --capital 50000 --risco-trade 0.5
    python -m cashinho.core.risk simular PETR4 compra 31.00 30.70
    python -m cashinho.core.risk kill-switch on --motivo "mercado maluco"
    python -m cashinho.core.risk novo-pregao

Configuracao e estado ficam em ``~/.cashinho`` (mude com ``--dados``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ...models import Direction
from .config import ConfiguracaoInvalidaError, RiskConfig
from .manager import RiskManager
from .models import PedidoOperacao, RiskRejectionError
from .state import RiskState
from .view import decisao as ver_decisao
from .view import pagina
from ..arquivos import escrever_json

PASTA_PADRAO = Path.home() / ".cashinho"


def _caminhos(pasta: Path) -> tuple[Path, Path]:
    return pasta / "risco.json", pasta / "risco-estado.json"


def carregar(pasta: Path) -> RiskManager:
    arq_config, arq_estado = _caminhos(pasta)
    config = RiskConfig.carregar(arq_config)
    estado = (
        RiskState.de_dict(json.loads(arq_estado.read_text()))
        if arq_estado.exists()
        else RiskState(capital_inicial=config.capital)
    )
    return RiskManager(config, estado)


def salvar(pasta: Path, rm: RiskManager) -> None:
    arq_config, arq_estado = _caminhos(pasta)
    rm.config.salvar(arq_config)
    arq_estado.parent.mkdir(parents=True, exist_ok=True)
    escrever_json(arq_estado, rm.estado.para_dict_completo())


def _direcao(texto: str) -> Direction:
    t = texto.strip().lower()
    if t in ("compra", "long", "c", "buy"):
        return Direction.LONG
    if t in ("venda", "short", "v", "sell"):
        return Direction.SHORT
    raise argparse.ArgumentTypeError(f"direcao invalida: {texto!r} (use compra ou venda)")


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-risco", description="Pagina Risk Manager do Cashinho")
    p.add_argument("--dados", type=Path, default=PASTA_PADRAO, help="pasta de configuracao e estado")
    p.add_argument("--sem-cor", action="store_true", help="desliga as cores ANSI")
    sub = p.add_subparsers(dest="comando")

    sub.add_parser("status", help="mostra a pagina (padrao)")

    cfg = sub.add_parser("configurar", help="ajusta os limites de risco")
    cfg.add_argument("--capital", type=float, help="capital disponivel (R$)")
    cfg.add_argument("--risco-trade", type=float, help="risco por trade (%% do capital)")
    cfg.add_argument("--risco-maximo", type=float, help="teto de risco por trade (R$)")
    cfg.add_argument("--perda-diaria", type=float, help="perda maxima diaria (%% do capital)")
    cfg.add_argument("--max-trades", type=int, help="maximo de trades por dia")
    cfg.add_argument("--exposicao-max", type=float, help="exposicao maxima total (%%)")
    cfg.add_argument("--exposicao-ativo", type=float, help="exposicao maxima por ativo (%%)")
    cfg.add_argument("--perdas-seguidas", type=int, help="maximo de perdas consecutivas")
    cfg.add_argument("--drawdown-max", type=float, help="drawdown maximo (%%)")

    sim = sub.add_parser("simular", help="pergunta ao risco se uma operacao passa")
    sim.add_argument("ativo")
    sim.add_argument("direcao", type=_direcao)
    sim.add_argument("entrada", type=float)
    sim.add_argument("stop", type=float)

    ks = sub.add_parser("kill-switch", help="liga ou desliga a trava geral")
    ks.add_argument("acao", choices=["on", "off"])
    ks.add_argument("--motivo", default="acionado manualmente")

    sub.add_parser("novo-pregao", help="zera os contadores do dia")
    return p


_CAMPOS_CONFIG = {
    "capital": "capital",
    "risco_trade": "risco_por_trade_pct",
    "risco_maximo": "risco_max_monetario",
    "perda_diaria": "perda_max_diaria_pct",
    "max_trades": "max_trades_dia",
    "exposicao_max": "exposicao_max_total_pct",
    "exposicao_ativo": "exposicao_max_por_ativo_pct",
    "perdas_seguidas": "max_perdas_consecutivas",
    "drawdown_max": "drawdown_max_pct",
}


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    cores = not args.sem_cor and sys.stdout.isatty()
    rm = carregar(args.dados)
    comando = args.comando or "status"

    if comando == "configurar":
        campos = {
            destino: getattr(args, origem)
            for origem, destino in _CAMPOS_CONFIG.items()
            if getattr(args, origem, None) is not None
        }
        if not campos:
            print("nada para configurar (veja --help)")
            return 2
        try:
            rm.atualizar_config(**campos)
        except ConfiguracaoInvalidaError as e:
            print(f"configuracao recusada: {e}")
            return 1
        salvar(args.dados, rm)
        print(f"limites atualizados: {', '.join(sorted(campos))}\n")

    elif comando == "simular":
        pedido = PedidoOperacao(args.ativo, args.direcao, args.entrada, args.stop)
        print(ver_decisao(rm.avaliar(pedido), cores))
        print()

    elif comando == "kill-switch":
        if args.acao == "on":
            rm.acionar_kill_switch(args.motivo)
        else:
            rm.liberar_kill_switch()
        salvar(args.dados, rm)

    elif comando == "novo-pregao":
        rm.novo_pregao()
        salvar(args.dados, rm)
        print("contadores do dia zerados\n")

    print(pagina(rm.status(), rm.config, cores))
    return 0 if rm.liberado else 1


if __name__ == "__main__":
    raise SystemExit(main())
