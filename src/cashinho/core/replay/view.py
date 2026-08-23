"""Tela do Market Replay."""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .eventos import EventoReplay, TipoEvento
from .grafico import grafico
from .replay import EstadoReplay, MarketReplay

LARGURA = 88

_CORES = {
    "verde": "\033[32m", "vermelho": "\033[31m", "amarelo": "\033[33m",
    "azul": "\033[36m", "cinza": "\033[90m", "negrito": "\033[1m", "reset": "\033[0m",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def barra_de_progresso(fracao: float, largura: int = 40) -> str:
    cheias = int(round(max(0.0, min(1.0, fracao)) * largura))
    return "█" * cheias + "·" * (largura - cheias)


def cabecalho(replay: MarketReplay, cores: bool = False) -> str:
    c = replay.config
    dia = c.dia.strftime("%d/%m/%Y") if c.dia else "serie inteira"
    return _c(
        f"MARKET REPLAY · {c.symbol} · {dia} · {c.timeframe_base} · {c.velocidade.value}",
        "negrito", ativo=cores,
    )


def painel_progresso(replay: MarketReplay, cores: bool = False) -> str:
    e = replay.estado
    fita = replay.fita
    instante = f"{fita.instante:%H:%M}" if fita.comecou else "--:--"
    return (
        f" {barra_de_progresso(fita.progresso)}  {fita.posicao + 1}/{fita.total}"
        f"  ({fita.progresso * 100:.0f}%)   agora: {instante}"
    )


def painel_pipeline(estado: EstadoReplay, cores: bool = False) -> str:
    linhas = [_c(" PIPELINE", "negrito", ativo=cores)]
    linhas.append(
        f"   sinais {estado.sinais}   oportunidades {estado.oportunidades}"
        f"   barrados no auditor {estado.barrados_auditor}"
        f"   barrados no risco {estado.barrados_risco}"
    )
    linhas.append(f"   entradas {estado.entradas}   saidas {estado.saidas}")
    return "\n".join(linhas)


def painel_conta(replay: MarketReplay, cores: bool = False) -> str:
    s = replay.saldo
    posicoes = replay.broker.get_positions()
    cor = "verde" if s.pnl_acumulado > 0 else ("vermelho" if s.pnl_acumulado < 0 else "cinza")
    linhas = [_c(" CONTA", "negrito", ativo=cores)]
    linhas.append(
        f"   patrimonio {formata_dinheiro(s.patrimonio)}"
        f"   caixa {formata_dinheiro(s.saldo)}"
        f"   P&L {_c(f'{s.pnl_acumulado:+.2f}', cor, ativo=cores)}"
    )
    if posicoes:
        for p in posicoes:
            linhas.append(
                f"   posicao aberta: {p.symbol} {p.direcao.value} {p.quantidade} @ "
                f"{formata_dinheiro(p.preco_medio)}"
            )
    else:
        linhas.append("   nenhuma posicao aberta")
    return "\n".join(linhas)


def ultimos_eventos(eventos: Sequence[EventoReplay], quantos: int = 6,
                    cores: bool = False) -> str:
    linhas = [_c(f" EVENTOS ({len(eventos)})", "negrito", ativo=cores)]
    if not eventos:
        linhas.append("   nada ainda")
        return "\n".join(linhas)
    for e in list(eventos)[-quantos:]:
        cor = {"sinal": "amarelo", "entrada": "azul", "stop": "vermelho",
               "alvo": "verde", "saida": "azul", "barrado": "cinza"}[e.tipo.value]
        linhas.append(
            f"   {e.ts:%H:%M} {_c(e.marcador, cor, ativo=cores)} "
            f"{e.tipo.value:<8s} {e.descricao}"
        )
    return "\n".join(linhas)


def pagina(replay: MarketReplay, cores: bool = False, altura: int = 16,
           largura: int = 72) -> str:
    """A tela do replay no instante atual."""
    linhas = [
        cabecalho(replay, cores),
        "─" * LARGURA,
        painel_progresso(replay, cores),
        "",
        grafico(replay.fita, replay.estado.eventos, altura, largura, cores),
        "",
        painel_pipeline(replay.estado, cores),
        "",
        painel_conta(replay, cores),
        "",
        ultimos_eventos(replay.estado.eventos, cores=cores),
    ]
    return "\n".join(linhas)


def resumo(replay: MarketReplay) -> str:
    e = replay.estado
    s = replay.saldo
    return (
        f"{replay.config.symbol} · {e.passos}/{replay.fita.total} candles · "
        f"{e.sinais} sinal(is) · {e.entradas} entrada(s) · "
        f"P&L {s.pnl_acumulado:+.2f}"
    )
