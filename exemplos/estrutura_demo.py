#!/usr/bin/env python3
"""Demonstracao da leitura de estrutura, sem precisar de dados de mercado.

    python exemplos/estrutura_demo.py

Gera um pregao sintetico (tendencia de alta com pullback no fim), roda a
analise e mostra as tres saidas da interface: resumo, grafico e painel.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cashinho.core.structure import analisar_estrutura, grafico, painel, resumo  # noqa: E402
from cashinho.models import BRT, Candle, Series  # noqa: E402


def pregao_sintetico(pontos, passos: int = 8, semente: int = 11) -> Series:
    random.seed(semente)
    closes = [pontos[0]]
    for destino in pontos[1:]:
        origem = closes[-1]
        for k in range(1, passos + 1):
            closes.append(origem + (destino - origem) * k / passos + random.gauss(0, 0.012))

    inicio = datetime(2026, 8, 20, 10, 0, tzinfo=BRT)
    candles = []
    anterior = closes[0]
    for i, fechamento in enumerate(closes):
        abertura = anterior
        candles.append(
            Candle(
                ts=inicio + timedelta(minutes=5 * i),
                open=abertura,
                high=max(abertura, fechamento) + abs(random.gauss(0, 0.02)),
                low=min(abertura, fechamento) - abs(random.gauss(0, 0.02)),
                close=fechamento,
                volume=random.uniform(8_000, 60_000),
            )
        )
        anterior = fechamento
    return Series("PETR4", "5m", candles)


def main() -> None:
    serie = pregao_sintetico([30.0, 30.8, 30.45, 31.6, 31.15, 32.6, 32.0])
    estrutura = analisar_estrutura(serie)

    print(resumo(estrutura, cores=True))
    print()
    print(grafico(serie, estrutura, altura=18, largura=56, cores=True))
    print()
    print(painel(estrutura, cores=True))


if __name__ == "__main__":
    main()
