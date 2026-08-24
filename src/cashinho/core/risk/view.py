"""Pagina do Risk Manager.

O que ela precisa responder em um piscar de olhos: **posso operar agora?**
Por isso o estado vem primeiro, em faixa larga - TRADING LIBERADO ou TRADING
BLOQUEADO - e so depois os limites, a configuracao e as posicoes.
"""

from __future__ import annotations

from typing import Optional

from ...models import formata_dinheiro
from .config import RiskConfig
from .models import LimiteUso, RiskDecision, RiskStatus
from ..ui import c as _c

LARGURA = 64

def _pct(valor: float) -> str:
    return f"{valor:.2f}%".replace(".", ",")


def barra(fracao: float, largura: int = 12) -> str:
    """Barra de uso de um limite (cheia = limite estourado)."""
    fracao = max(0.0, min(1.0, fracao))
    cheias = int(round(fracao * largura))
    return "█" * cheias + "·" * (largura - cheias)


# ---------------------------------------------------------------------------
# faixa de status
# ---------------------------------------------------------------------------


def faixa(status: RiskStatus, cores: bool = False) -> str:
    """A faixa que diz, sem rodeio, se da para operar."""
    rotulo = status.rotulo
    miolo = rotulo.center(LARGURA - 2)
    estilo = ("verde", "negrito") if status.liberado else ("vermelho", "negrito")
    linhas = [
        "╔" + "═" * (LARGURA - 2) + "╗",
        "║" + miolo + "║",
        "╚" + "═" * (LARGURA - 2) + "╝",
    ]
    return "\n".join(_c(l, *estilo, ativo=cores) for l in linhas)


# ---------------------------------------------------------------------------
# pagina completa
# ---------------------------------------------------------------------------


def pagina(status: RiskStatus, config: RiskConfig, cores: bool = False) -> str:
    """Pagina Risk Manager: status, limites, configuracao e posicoes."""
    linhas: list[str] = [faixa(status, cores)]

    pregao = status.pregao.strftime("%d/%m/%Y") if status.pregao else "-"
    resultado = status.pnl_dia
    cor_resultado = "verde" if resultado > 0 else ("vermelho" if resultado < 0 else "cinza")
    linhas.append(
        f" pregao {pregao} · patrimonio {formata_dinheiro(status.patrimonio)} · "
        f"resultado do dia {_c(f'{resultado:+.2f}'.replace('.', ','), cor_resultado, ativo=cores)}"
    )

    if not status.liberado:
        linhas.append("")
        linhas.append(_c(" MOTIVO DO BLOQUEIO", "vermelho", "negrito", ativo=cores))
        for motivo in status.motivos:
            linhas.append(_c(f"   ✖ {motivo}", "vermelho", ativo=cores))
        if status.kill_switch:
            linhas.append(
                _c(
                    f"   kill switch: {status.kill_switch.codigo} "
                    f"({'desarma no proximo pregao' if status.kill_switch.diario else 'so libera manualmente'})",
                    "vermelho",
                    ativo=cores,
                )
            )

    linhas.append("")
    linhas.append(_c(" LIMITES", "negrito", ativo=cores))
    for limite in status.limites:
        linhas.append("   " + _linha_limite(limite, cores))

    linhas.append("")
    linhas.append(_c(" CONFIGURACAO", "negrito", ativo=cores))
    linhas.extend(_bloco_config(status, config))

    linhas.append("")
    linhas.append(_c(" POSICOES", "negrito", ativo=cores))
    if not status.posicoes:
        linhas.append("   nenhuma posicao aberta")
    for p in status.posicoes:
        linhas.append(
            f"   {p.symbol:<8s} {p.direcao.value:<7s} {p.quantidade:>6d} @ "
            f"{formata_dinheiro(p.preco_medio):>12s}   exposicao {formata_dinheiro(p.exposicao)}"
            f"   stop {formata_dinheiro(p.stop)}"
        )
    return "\n".join(linhas)


def _linha_limite(limite: LimiteUso, cores: bool) -> str:
    fracao = (limite.usado / limite.limite) if limite.limite else 0.0
    if limite.unidade == "R$":
        usado = formata_dinheiro(limite.usado)
        teto = formata_dinheiro(limite.limite)
    else:
        usado = f"{limite.usado:.0f}"
        teto = f"{limite.limite:.0f} {limite.unidade}"
    cor = "vermelho" if limite.estourado else ("amarelo" if fracao >= 0.7 else "cinza")
    return (
        f"{limite.nome:<17s} {usado:>13s} / {teto:<16s} "
        f"[{_c(barra(fracao), cor, ativo=cores)}] {fracao * 100:>5.1f}%"
    )


def _bloco_config(status: RiskStatus, c: RiskConfig) -> list[str]:
    risco = c.risco_alvo(status.patrimonio)
    return [
        f"   capital                {formata_dinheiro(c.capital):>14s}",
        f"   risco por trade        {_pct(c.risco_por_trade_pct):>14s}   "
        f"= {formata_dinheiro(risco)} por operacao"
        + (f" (teto {formata_dinheiro(c.risco_max_monetario)})" if c.risco_max_monetario else ""),
        # medida sobre o capital da ABERTURA do pregao - o mesmo numero do
        # bloco LIMITES, senao a pagina mostraria dois limites diferentes
        f"   perda maxima diaria    {_pct(c.perda_max_diaria_pct):>14s}   "
        f"= {formata_dinheiro(c.perda_max_diaria(status.capital_pregao))}",
        f"   maximo de trades/dia   {c.max_trades_dia:>14d}",
        f"   exposicao maxima       {_pct(c.exposicao_max_total_pct):>14s}   "
        f"total · {_pct(c.exposicao_max_por_ativo_pct)} por ativo",
        f"   perdas seguidas max.   {c.max_perdas_consecutivas:>14d}",
        f"   drawdown maximo        {_pct(c.drawdown_max_pct):>14s}",
        f"   lote                   {c.lote:>14d}   "
        f"({'fracionario liberado' if c.permitir_fracionario else 'so lote padrao'})",
    ]


# ---------------------------------------------------------------------------
# decisao
# ---------------------------------------------------------------------------


def decisao(d: RiskDecision, cores: bool = False) -> str:
    """Mostra o veredito do risco sobre um pedido."""
    cabecalho = "APROVADO PELO RISCO" if d.allowed else "REJEITADO PELO RISCO"
    estilo = ("verde", "negrito") if d.allowed else ("vermelho", "negrito")
    linhas = [_c(f"{cabecalho}  ·  {d.symbol}", *estilo, ativo=cores), f"  {d.reason}"]

    if d.allowed:
        linhas += [
            f"  quantidade            {d.position_size}",
            f"  risco monetario       {formata_dinheiro(d.monetary_risk)}"
            f"  ({formata_dinheiro(d.risco_por_acao)} por acao)",
            f"  financeiro da ordem   {formata_dinheiro(d.exposicao_da_ordem)}",
            f"  exposicao resultante  {formata_dinheiro(d.portfolio_exposure)}"
            f"  ({_pct(d.exposicao_pct)} do patrimonio)",
        ]
    else:
        linhas.append(f"  quantidade            0")
        if len(d.rejeicoes) > 1:
            linhas.append("  outros motivos:")
            for r in d.rejeicoes[1:]:
                linhas.append(f"    · {r.mensagem}")
        linhas.append(f"  exposicao atual       {formata_dinheiro(d.portfolio_exposure)}")
    return "\n".join(linhas)


def resumo(status: RiskStatus, cores: bool = False) -> str:
    """Uma linha, para o cabecalho de outras telas."""
    cor = "verde" if status.liberado else "vermelho"
    partes = [
        _c(status.rotulo, cor, ativo=cores),
        f"patrimonio {formata_dinheiro(status.patrimonio)}",
        f"dia {status.pnl_dia:+.2f}".replace(".", ","),
        f"trades {status.trades_dia}",
        f"exposicao {_pct(status.exposicao_pct)}",
    ]
    if not status.liberado and status.motivos:
        partes.append(status.motivos[0])
    return " | ".join(partes)
