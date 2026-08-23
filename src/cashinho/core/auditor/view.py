"""A secao AUDITOR e a tela do fluxo completo."""

from __future__ import annotations

from typing import Optional

from .modelos import AuditResult, Severidade
from .pipeline import ResultadoFinal

LARGURA = 72

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def secao_auditor(auditoria: AuditResult, cores: bool = False) -> str:
    """A secao AUDITOR: favoraveis, contrarios, riscos e decisao."""
    linhas = [_c(" AUDITOR", "negrito", ativo=cores)]
    linhas.append(
        f"   tentei invalidar esta oportunidade em {len(auditoria.checagens)} frentes"
    )

    linhas.append("")
    linhas.append(_c("   FATORES FAVORAVEIS", "negrito", ativo=cores)
                  + _c("  (nao consegui invalidar)", "cinza", ativo=cores))
    if auditoria.favoraveis:
        for c in auditoria.favoraveis:
            linhas.append(f"     {_c('✔', 'verde', ativo=cores)} {c.titulo}: {c.detalhe}")
    else:
        linhas.append("     nenhuma frente saiu limpa")

    linhas.append("")
    linhas.append(_c("   FATORES CONTRARIOS", "negrito", ativo=cores))
    if auditoria.contrarios:
        for c in auditoria.contrarios:
            linhas.append(
                f"     {_c('!', 'amarelo', ativo=cores)} {c.titulo}: {c.detalhe}"
                + _c(f"  ({c.ajuste:+.0f} pts)", "cinza", ativo=cores)
            )
    else:
        linhas.append("     nenhum alerta")

    linhas.append("")
    linhas.append(_c("   RISCOS ENCONTRADOS", "negrito", ativo=cores)
                  + _c("  (rejeicao critica)", "cinza", ativo=cores))
    if auditoria.criticos:
        for c in auditoria.criticos:
            linhas.append(f"     {_c('✖', 'vermelho', ativo=cores)} {c.titulo}: {c.detalhe}")
    else:
        linhas.append("     nenhum risco critico")

    if auditoria.nao_verificadas:
        linhas.append("")
        linhas.append(_c("   NAO VERIFICADO", "cinza", ativo=cores))
        for c in auditoria.nao_verificadas:
            linhas.append(f"     ? {c.titulo}: {c.detalhe}")

    linhas.append("")
    linhas.append(_c("   DECISAO", "negrito", ativo=cores))
    cor = "verde" if auditoria.approved else "vermelho"
    veredito = "APROVADO PELO AUDITOR" if auditoria.approved else "REPROVADO PELO AUDITOR"
    linhas.append("     " + _c(veredito, cor, "negrito", ativo=cores))
    linhas.append(f"     {auditoria.motivo}")
    linhas.append(
        f"     score {auditoria.score_original:.0f} -> "
        + _c(f"{auditoria.score_final:.0f}", cor, ativo=cores)
        + f"  (ajuste {auditoria.score_adjustment:+.0f})"
    )
    return "\n".join(linhas)


def resumo_auditoria(auditoria: AuditResult) -> str:
    """Uma linha."""
    veredito = "aprovado" if auditoria.approved else "reprovado"
    return (
        f"auditor: {veredito} | {len(auditoria.favoraveis)} favoraveis, "
        f"{len(auditoria.contrarios)} alertas, {len(auditoria.criticos)} criticos | "
        f"score {auditoria.score_original:.0f} -> {auditoria.score_final:.0f}"
    )


# ---------------------------------------------------------------------------
# fluxo completo
# ---------------------------------------------------------------------------


def trilha_do_fluxo(resultado: ResultadoFinal, cores: bool = False) -> str:
    """As cinco etapas na ordem, com o veredito de cada uma."""
    linhas = [_c(" FLUXO", "negrito", ativo=cores)]
    for e in resultado.etapas:
        if not e.executada:
            linhas.append(_c(f"   ·  {e.ordem}. {e.nome}: nao executada", "cinza", ativo=cores))
            continue
        cor = "verde" if e.passou else "vermelho"
        linhas.append(
            f"   {_c(e.simbolo, cor, ativo=cores)}  {e.ordem}. {e.nome}: {e.detalhe}"
        )
    return "\n".join(linhas)


def pagina_resultado(resultado: ResultadoFinal, cores: bool = False) -> str:
    """A tela do fluxo inteiro, do sinal ao risco."""
    cor = "verde" if resultado.aprovado else "vermelho"
    rotulo = "OPERACAO LIBERADA" if resultado.aprovado else "OPERACAO BARRADA"
    linhas = [
        _c(f"RESULTADO FINAL · {resultado.symbol} · {resultado.instante:%d/%m %H:%M}",
           "negrito", ativo=cores),
        "─" * LARGURA,
        _c("╔" + "═" * (LARGURA - 2) + "╗", cor, "negrito", ativo=cores),
        _c("║" + rotulo.center(LARGURA - 2) + "║", cor, "negrito", ativo=cores),
        _c("╚" + "═" * (LARGURA - 2) + "╝", cor, "negrito", ativo=cores),
        f" {resultado.resumo}",
        "",
        trilha_do_fluxo(resultado, cores),
    ]

    if resultado.auditoria is not None:
        linhas.append("")
        linhas.append(secao_auditor(resultado.auditoria, cores))

    if resultado.decisao_de_risco is not None:
        from ..risk.view import decisao as ver_decisao

        linhas.append("")
        linhas.append(ver_decisao(resultado.decisao_de_risco, cores))
    return "\n".join(linhas)
