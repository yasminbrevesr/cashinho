"""Tela de noticias e eventos.

    python -m cashinho.core.noticias --arquivo eventos.json --ativo PETR4
    python -m cashinho.core.noticias --modelo > eventos.json
    python -m cashinho.core.noticias --arquivo eventos.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...models import BRT
from .fontes import FonteArquivo, SemFonte, VALIDADE_PADRAO_MIN
from .politica import ConfigEventos, PoliticaDeEventos
from .view import pagina

MODELO = {
    "_modelo": (
        "MODELO do calendario de eventos do Cashinho. Troque os eventos abaixo pelos "
        "reais - calendario do Banco Central, RI das companhias, agenda macro da sua "
        "corretora. Nenhum evento deste modelo e' real."
    ),
    "atualizado_em": "AAAA-MM-DDTHH:MM:SS-03:00",
    "fonte": "calendario manual",
    "eventos": [
        {
            "event_type": "decisao_de_juros | inflacao | payroll | resultados | "
                          "fato_relevante | evento_corporativo",
            "symbol": "vazio para evento de mercado inteiro; PETR4 para evento do ativo",
            "timestamp": "AAAA-MM-DDTHH:MM:SS-03:00",
            "severity": "critica | alta | media | baixa",
            "directional_bias": "alta | baixa | indefinido",
            "confidence": 0.9,
            "confirmado": True,
            "source": "de onde veio - obrigatorio",
            "titulo": "descricao curta",
        }
    ],
}


def _data(texto: str) -> datetime:
    try:
        ts = datetime.fromisoformat(texto)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"data invalida: {texto!r}") from e
    return ts.replace(tzinfo=BRT) if ts.tzinfo is None else ts


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cashinho-noticias",
        description="Agenda de noticias e eventos do Cashinho")
    p.add_argument("--arquivo", type=Path, help="calendario em JSON")
    p.add_argument("--ativo", default="", help="filtra os eventos deste ativo")
    p.add_argument("--instante", type=_data, help="avalia como se fosse este momento")
    p.add_argument("--validade-horas", type=float, default=VALIDADE_PADRAO_MIN / 60,
                   help="idade maxima da agenda antes de virar NOTICIAS INDISPONIVEIS")
    p.add_argument("--modelo", action="store_true",
                   help="imprime um calendario modelo para voce preencher")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sem-cor", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)

    if args.modelo:
        print(json.dumps(MODELO, indent=2, ensure_ascii=False))
        return 0

    fonte = (FonteArquivo(args.arquivo, validade_min=args.validade_horas * 60)
             if args.arquivo else SemFonte())
    agora = args.instante or datetime.now(BRT)
    agenda = fonte.carregar(agora)
    avaliacao = PoliticaDeEventos().avaliar(agenda, args.ativo, agora)

    if args.json:
        print(json.dumps({"agenda": agenda.para_dict(), "avaliacao": avaliacao.para_dict()},
                         indent=2, ensure_ascii=False))
        return 0

    print(pagina(agenda, agora, args.ativo,
                 cores=not args.sem_cor and sys.stdout.isatty(), avaliacao=avaliacao))
    if not args.arquivo:
        print("  informe --arquivo com o calendario, ou gere um com --modelo\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
