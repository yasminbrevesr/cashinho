"""Grafico do replay: candles e o que aconteceu em cima deles.

Cada coluna e' um candle - corpo cheio na alta, vazado na baixa, pavio fino.
Por cima entram os marcadores do que o pipeline decidiu: sinal, entrada,
stop, alvo e saida. So os candles que ja passaram sao desenhados; a fita nao
entrega os outros nem para desenhar.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Candle, formata_dinheiro
from .eventos import EventoReplay, TipoEvento
from .fita import FitaDeMercado

ALTA = "█"
BAIXA = "▒"
PAVIO = "│"
VAZIO = " "

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "azul": "\033[36m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_COR_DO_EVENTO = {
    TipoEvento.SINAL: "amarelo",
    TipoEvento.ENTRADA: "azul",
    TipoEvento.STOP: "vermelho",
    TipoEvento.ALVO: "verde",
    TipoEvento.SAIDA: "azul",
    TipoEvento.BARRADO: "cinza",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def grafico(
    fita: FitaDeMercado,
    eventos: Sequence[EventoReplay] = (),
    altura: int = 18,
    largura: int = 72,
    cores: bool = False,
) -> str:
    """Desenha os ultimos ``largura`` candles ja revelados, com os marcadores."""
    visivel = fita.visivel()
    if len(visivel) < 2:
        return "(aguardando candles)"

    candles = visivel.candles[-largura:]
    base = len(visivel) - len(candles)  # deslocamento na fita
    pmin = min(c.low for c in candles)
    pmax = max(c.high for c in candles)
    if pmax <= pmin:
        pmax = pmin + max(pmin * 0.001, 0.01)
    folga = (pmax - pmin) * 0.05
    pmin, pmax = pmin - folga, pmax + folga

    def linha_de(preco: float) -> Optional[int]:
        if not (pmin <= preco <= pmax):
            return None
        return int(round((pmax - preco) / (pmax - pmin) * (altura - 1)))

    grade = [[VAZIO] * len(candles) for _ in range(altura)]
    estilos: dict[tuple[int, int], str] = {}

    # 1) os candles
    for col, c in enumerate(candles):
        topo, base_pavio = linha_de(c.high), linha_de(c.low)
        corpo_alto = linha_de(max(c.open, c.close))
        corpo_baixo = linha_de(min(c.open, c.close))
        if None in (topo, base_pavio, corpo_alto, corpo_baixo):
            continue
        for l in range(topo, base_pavio + 1):
            grade[l][col] = PAVIO
        marca = ALTA if c.close >= c.open else BAIXA
        for l in range(corpo_alto, corpo_baixo + 1):
            grade[l][col] = marca
            estilos[(l, col)] = "verde" if c.close >= c.open else "vermelho"

    # 2) os marcadores por cima
    rotulos: dict[int, list[str]] = {}
    for e in eventos:
        col = e.indice - base
        if not (0 <= col < len(candles)):
            continue
        preco = e.preco if e.tipo is not TipoEvento.SINAL else candles[col].close
        linha = linha_de(preco)
        if linha is None:
            continue
        grade[linha][col] = e.marcador
        estilos[(linha, col)] = _COR_DO_EVENTO[e.tipo]
        if e.tipo in (TipoEvento.ENTRADA, TipoEvento.STOP, TipoEvento.ALVO):
            rotulos.setdefault(linha, [])
            marca = f"{e.marcador} {formata_dinheiro(e.preco)}"
            if marca not in rotulos[linha]:
                rotulos[linha].append(marca)

    # 3) montagem
    linhas = []
    for l in range(altura):
        preco = pmax - (pmax - pmin) * l / (altura - 1)
        corpo = "".join(
            _c(grade[l][col], estilos.get((l, col), ""), ativo=cores and (l, col) in estilos)
            for col in range(len(candles))
        )
        sufixo = ("  " + " · ".join(rotulos[l])) if l in rotulos else ""
        linhas.append(f"{formata_dinheiro(preco):>12s} ┤{corpo}{sufixo}")

    linhas.append(" " * 12 + " └" + "─" * len(candles))
    inicio, fim = candles[0].ts, candles[-1].ts
    espaco = max(len(candles) - 11, 1)
    linhas.append(" " * 13 + f"{inicio:%H:%M}{' ' * espaco}{fim:%H:%M}")
    linhas.append(
        "  " + _c(f"{ALTA} alta  {BAIXA} baixa  s sinal  E entrada  "
                  f"S stop  A alvo  X saida", "cinza", ativo=cores)
    )
    return "\n".join(linhas)
