"""Pagina Paper Trading na linha de comando.

    python -m cashinho.core.broker                       # a pagina
    python -m cashinho.core.broker preco PETR4 31.00
    python -m cashinho.core.broker comprar PETR4 500 --stop 30.70
    python -m cashinho.core.broker oco PETR4 500 --stop 30.70 --alvo 31.60
    python -m cashinho.core.broker cancelar --todas
    python -m cashinho.core.broker kill-switch on --motivo "fim do expediente"

Estado da conta simulada em ``~/.cashinho`` (mude com ``--dados``).

O comando ``preco`` faz o mercado andar: monta um candle naquele preco e
confere todas as ordens pendentes. E' um atalho - nao simula o caminho
dentro do candle.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...models import BRT, Candle, Direction
from ..backtest.costs import ModeloCustos
from ..risk.config import RiskConfig
from ..risk.manager import RiskManager
from ..risk.state import RiskState
from .modelos import Order, OrderType
from .paper import ConfigPaper, PaperBroker
from .risco import BrokerComRisco
from .view import pagina, resumo

PASTA_PADRAO = Path.home() / ".cashinho"


def _caminhos(pasta: Path) -> tuple[Path, Path, Path]:
    return pasta / "paper.json", pasta / "risco.json", pasta / "risco-estado.json"


def carregar(pasta: Path, capital: float) -> BrokerComRisco:
    arq_paper, arq_config, arq_estado = _caminhos(pasta)
    custos = ModeloCustos()
    if arq_paper.exists():
        dados = json.loads(arq_paper.read_text())
        paper = PaperBroker.de_dict(dados, ConfigPaper(
            capital_inicial=float(dados.get("capital_inicial", capital)), custos=custos))
    else:
        paper = PaperBroker(ConfigPaper(capital_inicial=capital, custos=custos))

    config = RiskConfig.carregar(arq_config)
    if config.capital != paper.config.capital_inicial:
        config = config.atualizar(capital=paper.config.capital_inicial)
    estado = (
        RiskState.de_dict(json.loads(arq_estado.read_text()))
        if arq_estado.exists()
        else RiskState(capital_inicial=config.capital)
    )
    return BrokerComRisco(paper, RiskManager(config, estado))


def salvar(pasta: Path, broker: BrokerComRisco) -> None:
    arq_paper, arq_config, arq_estado = _caminhos(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arq_paper.write_text(json.dumps(broker.broker.para_dict(), indent=2, ensure_ascii=False))
    broker.risco.config.salvar(arq_config)
    arq_estado.write_text(json.dumps(broker.risco.estado.para_dict_completo(), indent=2,
                                     ensure_ascii=False))


def _tipo(texto: str) -> OrderType:
    try:
        return OrderType(texto.lower())
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"tipo invalido: {texto!r} (use {', '.join(t.value for t in OrderType)})"
        ) from e


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-paper", description="Paper Trading do Cashinho")
    p.add_argument("--dados", type=Path, default=PASTA_PADRAO)
    p.add_argument("--capital", type=float, default=100_000.0, help="capital da conta nova")
    p.add_argument("--sem-cor", action="store_true")
    p.add_argument("--json", action="store_true", help="imprime o estado em JSON")

    # as mesmas opcoes valem depois do subcomando: SUPPRESS evita que o
    # default do subparser apague o que veio antes dele
    comuns = argparse.ArgumentParser(add_help=False)
    comuns.add_argument("--dados", type=Path, default=argparse.SUPPRESS)
    comuns.add_argument("--capital", type=float, default=argparse.SUPPRESS)
    comuns.add_argument("--sem-cor", action="store_true", default=argparse.SUPPRESS)
    comuns.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    sub = p.add_subparsers(dest="comando", parser_class=lambda **kw: argparse.ArgumentParser(
        parents=[comuns], **kw))

    sub.add_parser("status", help="mostra a pagina (padrao)")

    for nome, ajuda in (("comprar", "envia ordem de compra"), ("vender", "envia ordem de venda")):
        c = sub.add_parser(nome, help=ajuda)
        c.add_argument("ativo")
        c.add_argument("quantidade", type=int)
        c.add_argument("--tipo", type=_tipo, default=OrderType.MARKET)
        c.add_argument("--preco", type=float, help="limite, para ordem limitada")
        c.add_argument("--disparo", type=float, help="gatilho, para ordem stop")
        c.add_argument("--stop", type=float, help="stop de referencia (o risco exige)")

    o = sub.add_parser("oco", help="protecao: stop loss + take profit ligados")
    o.add_argument("ativo")
    o.add_argument("quantidade", type=int)
    o.add_argument("--stop", type=float, required=True)
    o.add_argument("--alvo", type=float, required=True)

    c = sub.add_parser("cancelar", help="cancela uma ordem ou todas")
    c.add_argument("id", nargs="?")
    c.add_argument("--todas", action="store_true")

    pr = sub.add_parser("preco", help="faz o mercado andar ate um preco")
    pr.add_argument("ativo")
    pr.add_argument("valor", type=float)

    ks = sub.add_parser("kill-switch", help="trava ou destrava a simulacao")
    ks.add_argument("acao", choices=["on", "off"])
    ks.add_argument("--motivo", default="acionado manualmente")

    sub.add_parser("reset", help="zera a conta simulada")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    comando = args.comando or "status"

    if comando == "reset":
        arq_paper, _, arq_estado = _caminhos(args.dados)
        for arq in (arq_paper, arq_estado):
            if arq.exists():
                arq.unlink()
        print(f"conta simulada zerada com {args.capital:,.2f}".replace(",", "."))
        broker = carregar(args.dados, args.capital)
        salvar(args.dados, broker)
        return 0

    broker = carregar(args.dados, args.capital)
    saida: list[str] = []

    if comando in ("comprar", "vender"):
        lado = Direction.LONG if comando == "comprar" else Direction.SHORT
        ordem = Order(
            symbol=args.ativo.upper(), side=lado, tipo=args.tipo,
            quantidade=args.quantidade, preco_limite=args.preco,
            preco_disparo=args.disparo, stop_referencia=args.stop,
        )
        enviada = broker.place_order(ordem)
        saida.append(f"{enviada.id}: {enviada.descricao} -> {enviada.status.value}")
        if enviada.motivo:
            saida.append(f"  {enviada.motivo}")
        salvar(args.dados, broker)

    elif comando == "oco":
        alvo = args.ativo.upper()
        posicao = next((p for p in broker.get_positions(alvo)), None)
        if posicao is None:
            print(f"nao ha posicao aberta em {alvo} para proteger")
            return 2
        lado = Direction.SHORT if posicao.quantidade > 0 else Direction.LONG
        sl, tp = broker.place_oco(
            Order(alvo, lado, OrderType.STOP_LOSS, args.quantidade, preco_disparo=args.stop),
            Order(alvo, lado, OrderType.TAKE_PROFIT, args.quantidade, preco_limite=args.alvo),
        )
        saida.append(f"OCO enviado: {sl.id} (stop) e {tp.id} (alvo)")
        salvar(args.dados, broker)

    elif comando == "cancelar":
        if args.todas:
            canceladas = broker.cancel_all()
            saida.append(f"{len(canceladas)} ordem(ns) cancelada(s)")
        elif args.id:
            try:
                o = broker.cancel_order(args.id)
            except Exception as e:
                print(f"nao foi possivel cancelar: {e}")
                return 2
            saida.append(f"{o.id}: {o.status.value}")
        else:
            print("informe o id da ordem ou use --todas")
            return 2
        salvar(args.dados, broker)

    elif comando == "preco":
        alvo, valor = args.ativo.upper(), args.valor
        agora = datetime.now(BRT)
        executadas = broker.processar(alvo, Candle(agora, valor, valor, valor, valor, 0.0))
        broker.broker.atualizar_preco(alvo, valor)
        saida.append(f"{alvo} a {valor:.2f}: {len(executadas)} ordem(ns) executada(s)")
        for o in executadas:
            saida.append(f"  {o.id} {o.tipo.value} a {o.preco_executado:.2f}")
        salvar(args.dados, broker)

    elif comando == "kill-switch":
        if args.acao == "on":
            canceladas = broker.acionar_kill_switch(args.motivo)
            saida.append(f"KILL SWITCH ACIONADO - {len(canceladas)} ordem(ns) cancelada(s)")
        else:
            broker.liberar_kill_switch()
            saida.append("kill switch liberado")
        salvar(args.dados, broker)

    if args.json:
        print(json.dumps({
            "saldo": broker.get_balance().para_dict(),
            "posicoes": [p.para_dict() for p in broker.get_positions()],
            "ordens": [o.para_dict() for o in broker.get_orders()],
            "operacoes": [o.para_dict() for o in broker.get_trades()],
        }, indent=2, ensure_ascii=False))
        return 0

    for linha in saida:
        print(linha)
    if saida:
        print()
    cores = not args.sem_cor and sys.stdout.isatty()
    print(pagina(broker, cores))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
