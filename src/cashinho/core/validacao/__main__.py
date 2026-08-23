"""Validacao de estrategias na linha de comando.

    python -m cashinho.core.validacao --ativo PETR4 --dias 30
    python -m cashinho.core.validacao --percentuais 70,15,15
    python -m cashinho.core.validacao --fim-treino 2026-08-10 --fim-validacao 2026-08-15
    python -m cashinho.core.validacao --walk-forward --treino 10 --teste 5
    python -m cashinho.core.validacao --sem-teste     # deixa o cofre fechado
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from ...data.base import DataError
from ...data.csv_provider import CSVProvider
from ...data.synthetic import SyntheticProvider
from ..backtest.config import BacktestConfig
from ..backtest.costs import ModeloCustos
from ..oportunidade.estrategia import EstrategiaOportunidade
from ..risk.config import RiskConfig
from .divisao import DivisaoDeDados, DivisaoInvalidaError
from .validador import ConfigValidacao, ValidadorDeEstrategia
from .view import pagina, pagina_walk_forward
from .walkforward import ConfigWalkForward, walk_forward


def _data(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"data invalida: {texto!r} (use AAAA-MM-DD)") from e


def _percentuais(texto: str) -> tuple[float, float, float]:
    partes = [p.strip() for p in texto.split(",")]
    if len(partes) != 3:
        raise argparse.ArgumentTypeError("informe tres numeros: treino,validacao,teste")
    try:
        valores = [float(p) for p in partes]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"percentuais invalidos: {texto!r}") from e
    total = sum(valores)
    # aceita as duas escalas usuais - 0.6,0.2,0.2 e 60,20,20 - e recusa o resto.
    # reescalar qualquer soma seria conveniente e silencioso: "0.5,0.3,0.3" viraria
    # 45/27/27 sem ninguem avisar, e a divisao pedida nao seria a divisao feita
    if abs(total - 1.0) < 1e-6:
        escala = 1.0
    elif abs(total - 100.0) < 1e-6:
        escala = 100.0
    else:
        raise argparse.ArgumentTypeError(
            f"os percentuais somam {total:g}: use fracoes que somem 1 "
            "(0.6,0.2,0.2) ou porcentagens que somem 100 (60,20,20)")
    if any(v <= 0 for v in valores):
        raise argparse.ArgumentTypeError("nenhuma particao pode ficar com zero")
    return tuple(v / escala for v in valores)  # type: ignore[return-value]


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cashinho-validacao",
                                description="Validacao de estrategias do Cashinho")

    dados = p.add_argument_group("dados")
    dados.add_argument("--ativo", default="PETR4")
    dados.add_argument("--fonte", choices=["demo", "csv", "yahoo"], default="demo")
    dados.add_argument("--pasta", type=Path, default=Path("dados"))
    dados.add_argument("--dias", type=int, default=30)
    dados.add_argument("--timeframe", default="1m")
    dados.add_argument("--semente", type=int, default=3)

    divisao = p.add_argument_group("divisao")
    divisao.add_argument("--percentuais", type=_percentuais, default=(0.6, 0.2, 0.2),
                         metavar="T,V,TE", help="proporcoes de treino, validacao e teste")
    divisao.add_argument("--fim-treino", type=_data, help="divide por data em vez de proporcao")
    divisao.add_argument("--fim-validacao", type=_data)

    conta = p.add_argument_group("conta")
    conta.add_argument("--capital", type=float, default=100_000.0)
    conta.add_argument("--risco-trade", type=float, default=0.5, help="%% do capital")

    modo = p.add_argument_group("modo")
    modo.add_argument("--walk-forward", action="store_true")
    modo.add_argument("--treino", type=int, default=10, help="pregoes de treino por ciclo")
    modo.add_argument("--teste", type=int, default=5, help="pregoes fora da amostra por ciclo")
    modo.add_argument("--passo", type=int, help="pregoes a avancar entre ciclos")
    modo.add_argument("--sem-teste", action="store_true",
                      help="nao abre o cofre do TEST nesta rodada")

    saida = p.add_argument_group("saida")
    saida.add_argument("--json", action="store_true")
    saida.add_argument("--sem-cor", action="store_true")
    return p


def menor_camada_do_pipeline() -> str:
    """O timeframe mais fino que o pipeline le - o gatilho."""
    from ..confluencia.engine import CAMADAS_CONFLUENCIA
    from ..mtf.timeframes import parse_timeframe

    return min(CAMADAS_CONFLUENCIA.values(),
               key=lambda tf: parse_timeframe(tf).duracao_minutos(10_000))


def timeframe_serve_de_base(timeframe: str) -> bool:
    """A base precisa ser fina o bastante para gerar a menor camada do pipeline."""
    from ..mtf.timeframes import parse_timeframe

    try:
        base = parse_timeframe(timeframe)
        menor = parse_timeframe(menor_camada_do_pipeline())
    except Exception:
        return False
    return menor.eh_multiplo_de(base)


def carregar_serie(args):
    if args.fonte == "demo":
        return SyntheticProvider(semente=args.semente).candles(
            args.ativo, args.timeframe, args.dias)
    if args.fonte == "csv":
        return CSVProvider(args.pasta).candles(args.ativo, args.timeframe, args.dias)
    from ...data.yahoo import YahooProvider

    return YahooProvider().candles(args.ativo, args.timeframe, args.dias)


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        serie = carregar_serie(args)
    except DataError as e:
        print(f"nao foi possivel carregar os dados: {e}")
        return 2

    # a estrategia de oportunidade le o gatilho no 1m: uma base maior que isso
    # nao consegue montar as camadas, e o erro precisa dizer isso em vez de
    # sair como traceback de dentro do motor multi-timeframe
    if not timeframe_serve_de_base(args.timeframe):
        print(f"timeframe base {args.timeframe}: o pipeline le o gatilho em "
              f"{menor_camada_do_pipeline()}, que nao sai de um candle de {args.timeframe} "
              "(as camadas superiores saem do resample; as menores, nao)")
        return 2

    config = ConfigValidacao(backtest=BacktestConfig(
        symbol=args.ativo.upper(),
        timeframe_base=args.timeframe,
        capital_inicial=args.capital,
        risco=RiskConfig(capital=args.capital, risco_por_trade_pct=args.risco_trade),
        custos=ModeloCustos(),
    ))
    validador = ValidadorDeEstrategia(EstrategiaOportunidade, config)
    cores = not args.sem_cor and sys.stdout.isatty()

    if args.walk_forward:
        resultado = walk_forward(
            validador, serie,
            ConfigWalkForward(dias_de_treino=args.treino, dias_de_teste=args.teste,
                              passo=args.passo),
            config.backtest,
        )
        if args.json:
            print(json.dumps(resultado.para_dict(), indent=2, ensure_ascii=False))
        else:
            print(pagina_walk_forward(resultado, cores))
        return 0

    try:
        if args.fim_treino and args.fim_validacao:
            divisao = DivisaoDeDados.por_data(serie, args.fim_treino, args.fim_validacao)
        elif args.fim_treino or args.fim_validacao:
            print("divisao por data exige --fim-treino E --fim-validacao")
            return 2
        else:
            divisao = DivisaoDeDados.por_percentual(serie, *args.percentuais)
    except DivisaoInvalidaError as e:
        print(f"divisao invalida: {e}")
        return 2

    relatorio = validador.validar(divisao, medir_teste=not args.sem_teste)
    if args.json:
        print(json.dumps(relatorio.para_dict(), indent=2, ensure_ascii=False))
        return 0

    print(pagina(relatorio, cores))
    if args.fonte == "demo":
        print("\n  fonte: dados sinteticos (--fonte demo). Nao sao precos reais.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
