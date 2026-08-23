"""Secao ANALISE MULTI-TIMEFRAME.

Mostra o estado de cada periodo e - tao importante quanto - **quando** cada
leitura foi feita. Um contexto de 60m lido as 12:37 refere-se ao candle que
fechou as 12:00: a coluna de idade deixa isso na cara, em vez de dar a
impressao de que as quatro camadas sao igualmente recentes.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .estados import Vies
from .modelos import LeituraMultiTimeframe
from .regras import AvaliacaoRegra

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_SETA = {Vies.BULLISH: "▲ alta", Vies.BEARISH: "▼ baixa", Vies.NEUTRAL: "· neutro"}
_COR_DO_VIES = {Vies.BULLISH: "verde", Vies.BEARISH: "vermelho", Vies.NEUTRAL: "cinza"}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def _forca(valor: float, largura: int = 5) -> str:
    cheias = int(round(max(0.0, min(1.0, valor)) * largura))
    return "█" * cheias + "·" * (largura - cheias)


def _idade(minutos: float) -> str:
    if minutos < 1:
        return "agora"
    if minutos < 60:
        return f"{minutos:.0f} min"
    return f"{minutos / 60:.1f} h"


def secao_multitimeframe(
    leitura: LeituraMultiTimeframe,
    avaliacoes: Sequence[AvaliacaoRegra] = (),
    cores: bool = False,
    detalhar_razoes: bool = True,
) -> str:
    """A secao que entra na tela Analise."""
    linhas = [_c(" ANALISE MULTI-TIMEFRAME", "negrito", ativo=cores)]
    linhas.append(
        f"   {'camada':<9s} {'TF':<5s} {'estado':<22s} {'vies':<9s} {'forca':<6s} "
        f"{'fechou':<7s} {'idade':<7s}"
    )
    linhas.append("   " + "─" * 70)

    if not leitura.camadas:
        linhas.append("   nenhuma camada disponivel neste instante")
    for c in leitura.camadas:
        cor = _COR_DO_VIES[c.vies]
        linhas.append(
            f"   {c.papel:<9s} {c.timeframe:<5s} "
            + _c(f"{c.valor:<22s}", cor, ativo=cores)
            + f" {_SETA[c.vies]:<9s} {_forca(c.forca):<6s} "
            f"{c.fechado_em:%H:%M}   {_idade(c.idade_minutos):<7s}"
        )
        if detalhar_razoes and c.razoes:
            linhas.append(f"   {'':<9s} {'':<5s} └ {c.razoes[0]}")

    for papel in leitura.faltando:
        linhas.append(f"   {papel:<9s} {'-':<5s} " + _c("sem candle fechado ainda", "cinza", ativo=cores))

    alinhado = leitura.vies_alinhado()
    linhas.append("")
    if alinhado is not None:
        linhas.append(
            "   alinhamento: " + _c(
                f"as camadas apontam para {alinhado.value}", _COR_DO_VIES[alinhado], ativo=cores
            )
        )
    else:
        linhas.append("   alinhamento: " + _c("camadas em desacordo", "amarelo", ativo=cores))

    if avaliacoes:
        linhas.append("")
        linhas.append(_c("   REGRAS DE CONFLUENCIA", "negrito", ativo=cores))
        for a in avaliacoes:
            if a.satisfeita:
                linhas.append("   " + _c(f"✔ {a.regra.nome}", "verde", ativo=cores)
                              + f"  (confianca {a.confianca:.0%})")
            else:
                falha = a.falhas[0] if a.falhas else None
                detalhe = ""
                if falha is not None:
                    esperado = "/".join(falha.esperado)
                    detalhe = f" — {falha.papel}: {falha.obtido or '-'} (esperado {esperado})"
                    if falha.observacao:
                        detalhe += f" [{falha.observacao}]"
                linhas.append("   " + _c(f"✖ {a.regra.nome}", "cinza", ativo=cores) + detalhe)

    if leitura.avisos:
        linhas.append("")
        for aviso in leitura.avisos:
            linhas.append("   " + _c(f"· {aviso}", "cinza", ativo=cores))
    return "\n".join(linhas)


def linha_resumo(leitura: LeituraMultiTimeframe) -> str:
    """Uma linha: ``60m:bullish 15m:bullish 5m:pullback 1m:breakout_with_volume``."""
    return " ".join(f"{c.timeframe}:{c.valor}" for c in leitura.camadas)
