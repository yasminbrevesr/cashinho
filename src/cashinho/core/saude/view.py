"""A tela SYSTEM HEALTH.

Um painel de saude tem uma tentacao: mostrar verde. Esta tela faz o contrario
- componente sem noticia aparece, erro recente aparece, e a faixa do topo diz
em letra grande quando operacao nova esta bloqueada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from .estados import EstadoDeSaude, Modo
from .modelos import Componente, SaudeDoSistema
from .telemetria import RegistroDeErro

LARGURA = 72

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_COR_DO_ESTADO = {
    EstadoDeSaude.ONLINE: "verde",
    EstadoDeSaude.DEGRADED: "amarelo",
    EstadoDeSaude.OFFLINE: "vermelho",
}

_SIMBOLO = {
    EstadoDeSaude.ONLINE: "●",
    EstadoDeSaude.DEGRADED: "◐",
    EstadoDeSaude.OFFLINE: "○",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def _hora(ts: Optional[datetime], instante: Optional[datetime] = None) -> str:
    if ts is None:
        return "-"
    if instante is not None and ts.date() != instante.date():
        return ts.strftime("%d/%m %H:%M")
    return ts.strftime("%H:%M:%S")


def _latencia(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def linha_do_componente(c: Componente, instante: datetime, cores: bool = False) -> str:
    estado = _c(f"{_SIMBOLO[c.estado]} {c.estado.value:<9}", _COR_DO_ESTADO[c.estado],
                ativo=cores)
    erros = f"{c.n_erros}" if c.n_erros else "-"
    return (f"  {c.nome:<17}{estado}{_hora(c.ultimo_timestamp, instante):>15}"
            f"{_latencia(c.latencia_ms):>10}{erros:>8}")


def faixa_de_operacao(saude: SaudeDoSistema, cores: bool = False) -> str:
    bloqueado = saude.bloqueia_novas_operacoes
    estilo = ("vermelho", "negrito") if bloqueado else ("verde", "negrito")
    rotulo = saude.rotulo_operacao.center(LARGURA - 2)
    linhas = ["╔" + "═" * (LARGURA - 2) + "╗",
              "║" + rotulo + "║",
              "╚" + "═" * (LARGURA - 2) + "╝"]
    return "\n".join(_c(l, *estilo, ativo=cores) for l in linhas)


def secao_erros(erros: Sequence[RegistroDeErro], instante: datetime,
                limite: int = 5, cores: bool = False) -> str:
    if not erros:
        return "  ERROS RECENTES\n    nenhum erro na janela observada"
    linhas = [f"  ERROS RECENTES ({len(erros)})"]
    for e in erros[:limite]:
        linhas.append("    " + _c(f"{_hora(e.quando, instante)}  {e.componente:<14}"
                                  f"{e.mensagem}", "vermelho", ativo=cores))
    if len(erros) > limite:
        linhas.append(f"    ... e mais {len(erros) - limite}")
    return "\n".join(linhas)


def pagina(saude: SaudeDoSistema, cores: bool = False) -> str:
    """A tela completa do System Health."""
    instante = saude.timestamp
    geral = saude.estado_geral
    linhas = [
        "",
        _c(f"SYSTEM HEALTH · {instante:%d/%m %H:%M:%S}", "negrito", ativo=cores),
        "─" * LARGURA,
        faixa_de_operacao(saude, cores),
    ]

    if saude.bloqueios:
        for motivo in saude.bloqueios:
            linhas.append("  " + _c(f"✖ {motivo}", "vermelho", ativo=cores))

    linhas.append("")
    # "ultimo sinal" e nao "ultimo dado": para Market Data e' o timestamp do
    # candle; para os demais, a ultima vez que o componente deu sinal de vida
    linhas.append(f"  {'COMPONENTE':<17}{'ESTADO':<11}{'ULTIMO SINAL':>15}"
                  f"{'LATENCIA':>10}{'ERROS':>8}")
    linhas.append("  " + "─" * (LARGURA - 4))
    for c in saude.componentes:
        linhas.append(linha_do_componente(c, instante, cores))
        detalhe = c.detalhe
        if c.modo:
            detalhe = f"[{c.modo}] {detalhe}" if detalhe else f"[{c.modo}]"
        if detalhe:
            linhas.append(f"  {'':<17}└ {detalhe}")

    linhas.append("")
    linhas.append(_c("  SISTEMA", "negrito", ativo=cores))
    linhas.append(f"    estado geral    "
                  + _c(geral.value, _COR_DO_ESTADO[geral], ativo=cores)
                  + f"  ({geral.descricao})")
    linhas.append(f"    modo atual      {saude.modo.value}  ({saude.modo.descricao})")
    kill = ("ACIONADO - " + str(getattr(saude.kill_switch, "motivo", ""))
            if saude.kill_switch_ativo else "livre")
    linhas.append(f"    kill switch     "
                  + _c(kill, "vermelho" if saude.kill_switch_ativo else "verde",
                       ativo=cores))
    linhas.append(f"    ultima analise  {_hora(saude.ultima_analise, instante)}")

    linhas.append("")
    linhas.append(secao_erros(saude.erros, instante, cores=cores))
    linhas.append("")
    return "\n".join(linhas)


def linha_resumo(saude: SaudeDoSistema) -> str:
    """Uma linha para caber no topo de outra tela."""
    fora = [c.nome for c in saude.componentes if not c.estado.saudavel]
    estado = saude.estado_geral.value
    if not fora:
        return f"SAUDE {estado} · {saude.modo.value}"
    return f"SAUDE {estado} · {saude.modo.value} · atencao: {', '.join(fora)}"
