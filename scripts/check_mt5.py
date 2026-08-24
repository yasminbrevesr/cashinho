#!/usr/bin/env python3
"""Diagnostico do MetaTrader 5 da Genial - independente do resto do Cashinho.

    python scripts/check_mt5.py
    python scripts/check_mt5.py --ativo PETR4 --timeframe 5m

Roda os passos na ordem em que eles costumam falhar, e para no primeiro
problema com a instrucao do que fazer. Nao envia ordem nenhuma: este script
so le.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# permite rodar direto do repositorio, sem instalar
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from cashinho.data.base import DataError                     # noqa: E402
from cashinho.data.metatrader import (                       # noqa: E402
    MetaTraderMarketDataProvider,
    SimboloAmbiguoError,
    SimboloNaoEncontradoError,
)
from cashinho.settings import carregar                       # noqa: E402

OK, FALHA, AVISO = "  [ok]   ", "  [FALHA]", "  [aviso]"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnostico do MetaTrader 5 / Genial")
    p.add_argument("--ativo", default="PETR4")
    p.add_argument("--timeframe", default="1m")
    args = p.parse_args(argv)

    print("\nDIAGNOSTICO METATRADER 5 / GENIAL")
    print("=" * 60)

    provedor = MetaTraderMarketDataProvider(carregar())

    # 1. biblioteca
    if not provedor.disponivel:
        print(f"{FALHA} biblioteca MetaTrader5 nao encontrada")
        print("         instale na maquina do terminal: pip install MetaTrader5")
        print("         (ela so existe no Windows)")
        return 2
    print(f"{OK} biblioteca MetaTrader5 encontrada")

    # 2. terminal
    info = provedor.conectar()
    if not info.conectado:
        print(f"{FALHA} terminal nao conectado")
        print(f"         {info.motivo}")
        print("         abra o MetaTrader da Genial e autentique manualmente")
        return 2
    print(f"{OK} terminal conectado   {info.empresa}")
    print(f"{OK} servidor             {info.servidor}")

    # 3. simbolo
    try:
        resolucao = provedor.resolver_simbolo(args.ativo)
    except SimboloAmbiguoError as e:
        print(f"{FALHA} simbolo ambiguo: {e}")
        return 2
    except SimboloNaoEncontradoError as e:
        print(f"{FALHA} {e}")
        print("         abra a Observacao do Mercado (Ctrl+M), depois Ctrl+U, "
              "e adicione o ativo")
        return 2
    marca = "exato" if resolucao.exato else "APROXIMADO"
    print(f"{OK} simbolo resolvido    {resolucao.resolvido} ({marca})")

    # 4. cotacao
    try:
        cot = provedor.cotacao(args.ativo)
    except DataError as e:
        print(f"{FALHA} cotacao: {e}")
        return 2

    print(f"{OK} status do feed       {cot.status.value}")
    if cot.tem_livro:
        print(f"{OK} bid / ask            {cot.bid} / {cot.ask}   "
              f"(spread {cot.spread:.2f})")
    else:
        print(f"{AVISO} bid / ask            SEM LIVRO ATIVO "
              "(bid/ask zerados no terminal)")
    print(f"{OK} ultimo negocio       {cot.last}  volume {cot.volume}")
    print(f"{OK} cotacao em           {cot.quote_timestamp}")
    print(f"{OK} negocio em           {cot.trade_timestamp}")
    print(f"{OK} idade do dado        {cot.idade_legivel}")

    # 5. candles
    try:
        serie = provedor.candles(args.ativo, args.timeframe, 2)
        ultimo = serie.candles[-1]
        print(f"{OK} candles {args.timeframe:<12} {len(serie)} fechado(s), "
              f"ultimo {ultimo.ts:%d/%m %H:%M} close {ultimo.close}")
    except DataError as e:
        print(f"{AVISO} candles {args.timeframe}: {e}")

    # 6. livro de ofertas
    tem_livro = provedor.livro_disponivel(args.ativo)
    print(f"{OK if tem_livro else AVISO} market depth         "
          f"{'disponivel' if tem_livro else 'indisponivel neste terminal'}")

    # 7. a trava
    print(f"{OK} trading real         BLOQUEADO (capacidade trading=False)")

    print("=" * 60)
    print(f"  {resolucao.resolvido} {cot.status.value} - "
          f"fonte MetaTrader 5 / Genial\n")
    return 0 if cot.status.value in ("ONLINE", "NO_ACTIVE_BOOK", "MARKET_CLOSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
