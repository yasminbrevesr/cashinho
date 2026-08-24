"""As telas do Advisor: o card do dashboard e a visao detalhada.

Regra da casa, mantida: **nenhum numero sem a conta que o gerou**. O card
mostra o resultado; a visao detalhada abre as seis notas de cada timeframe,
com a leitura que justifica cada uma - e marca em cinza o que nao existe, em
vez de inventar zero.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..ui import c, hora, num
from .amostra import NivelDeConfianca
from .modelos import ItemDoRanking, StatusAdvisor, TimeframeRecommendation

LARGURA = 78

_COR_DO_STATUS = {
    StatusAdvisor.RECOMENDADO: "verde",
    StatusAdvisor.MANTER_ATUAL: "verde",
    StatusAdvisor.CONFIANCA_BAIXA: "amarelo",
    StatusAdvisor.DADOS_INSUFICIENTES: "cinza",
}

_COR_DA_CONFIANCA = {
    NivelDeConfianca.ALTA: "verde",
    NivelDeConfianca.MEDIA: "amarelo",
    NivelDeConfianca.BAIXA: "amarelo",
    NivelDeConfianca.INSUFICIENTE: "vermelho",
}


def _barra(nota: Optional[float], largura: int = 10) -> str:
    if nota is None:
        return "·" * largura
    cheias = int(round(max(0.0, min(100.0, nota)) / 100 * largura))
    return "█" * cheias + "·" * (largura - cheias)


def _nota(valor: Optional[float]) -> str:
    return "  -" if valor is None else f"{valor:3.0f}"


def card(rec: TimeframeRecommendation, cores: bool = False) -> str:
    """O card do dashboard - curto, com o essencial."""
    cor = _COR_DO_STATUS[rec.status]
    linhas = [
        c(" TIMEFRAME ADVISOR", "negrito", ativo=cores),
        f"   Ativo         {rec.symbol}",
    ]

    if not rec.tem_recomendacao:
        linhas.append("   " + c(rec.status.rotulo, cor, "negrito", ativo=cores))
        linhas.append(f"   {rec.status.descricao}")
        for aviso in rec.warnings[:2]:
            linhas.append("   " + c(f"! {aviso}", "amarelo", ativo=cores))
        return "\n".join(linhas)

    nivel = rec.confianca.nivel if rec.confianca else NivelDeConfianca.INSUFICIENTE
    linhas += [
        "",
        f"   {'Contexto':<13}{rec.context_timeframe or '-'}",
        f"   {'Setup':<13}" + c(rec.setup_timeframe or "-", cor, "negrito", ativo=cores),
        f"   {'Gatilho':<13}{rec.trigger_timeframe or '-'}",
        "",
        f"   {'Score':<13}{rec.market_fit_score:.0f}/100",
        f"   {'Confianca':<13}" + c(nivel.value, _COR_DA_CONFIANCA[nivel], ativo=cores),
        f"   {'Regime':<13}{rec.regime or 'indefinido'}",
        f"   {'Periodo':<13}{rec.periodo.rotulo}",
    ]

    if rec.rankings:
        linhas.append("")
        linhas.append(f"   {'RANKING':<13}")
        for item in rec.rankings[:6]:
            marca = "◄" if item.timeframe == rec.setup_timeframe else " "
            linhas.append(f"     {item.timeframe:<5}{_barra(item.total)} "
                          f"{item.total:5.1f} {marca}")

    if rec.reasons:
        linhas.append("")
        for motivo in rec.reasons[:3]:
            linhas.append(f"   · {motivo}")
    if rec.warnings:
        for aviso in rec.warnings[:2]:
            linhas.append("   " + c(f"! {aviso}", "amarelo", ativo=cores))
    return "\n".join(linhas)


def linha_detalhada(item: ItemDoRanking, cores: bool = False) -> str:
    """Uma linha por timeframe com as seis notas abertas."""
    notas = " ".join(
        f"{_nota(item.score.componente(k).nota if item.score.componente(k) else None)}"
        for k in ("regime", "estrutura", "ruido", "liquidez", "performance",
                  "estabilidade"))
    evidencia = ("  -" if item.statistical_evidence is None
                 else f"{item.statistical_evidence:3.0f}")
    return (f"  {item.timeframe:<5}{item.total:6.1f} {_barra(item.total)}  "
            f"{notas}   {item.market_fit:5.1f} {evidencia}  "
            f"{item.confianca.valor:5.1f}  {item.medidas.candles:>5}")


def pagina(rec: TimeframeRecommendation, cores: bool = False) -> str:
    """A visao detalhada: todo timeframe, toda nota, toda ausencia."""
    partes = ["", c(f"TIMEFRAME ADVISOR · {rec.symbol} · "
                    f"{hora(rec.as_of, segundos=True)}", "negrito", ativo=cores),
              "─" * LARGURA, card(rec, cores)]

    if rec.rankings:
        partes += [
            "",
            c(" DETALHE POR TIMEFRAME", "negrito", ativo=cores),
            f"  {'TF':<5}{'SCORE':>6} {'':<10}  {'REG EST RUI LIQ PER EST':<23}"
            f"   {'FIT':>5} {'EVI':>3}  {'CONF':>5}  {'CDL':>5}",
            "  " + "─" * (LARGURA - 4),
        ]
        for item in rec.rankings:
            partes.append(linha_detalhada(item, cores))

        lider = rec.item(rec.setup_timeframe or "") or rec.lider
        if lider is not None:
            partes.append("")
            partes.append(c(f" POR QUE {lider.timeframe}", "negrito", ativo=cores))
            for comp in lider.score.componentes:
                marca = "·" if not comp.disponivel else " "
                partes.append(f"   {marca} {comp.nome:<14}{_nota(comp.nota)}  "
                              f"peso {comp.peso:.2f}  {comp.leitura}")
            if lider.estatistica is not None:
                partes.append(f"   · {'Historico':<14}     "
                              f"        {lider.estatistica.leitura}")

    if rec.warnings:
        partes.append("")
        partes.append(c(" AVISOS", "negrito", ativo=cores))
        for aviso in rec.warnings:
            partes.append("   " + c(f"! {aviso}", "amarelo", ativo=cores))

    partes.append("")
    partes.append(c("  market fit e' leitura do comportamento de agora; evidencia "
                    "estatistica\n  precisa de historico. Os dois nunca viram um "
                    "numero so.", "cinza", ativo=cores))
    partes.append("")
    return "\n".join(partes)
