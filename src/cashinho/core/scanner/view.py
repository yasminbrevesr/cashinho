"""Tela do Scanner: a tabela do ranking e o detalhe de um ativo.

A tabela e' a forma certa aqui - sao nove colunas por ativo, e nenhum grafico
mostra isso sem virar enfeite. A coluna Status responde a pergunta que mais
importa quando nada foi liberado: *onde cada ativo parou?*
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .scanner import LinhaScanner, ResultadoScanner, StatusAtivo
from ..ui import c as _c

LARGURA = 108

_COR_DO_STATUS = {
    StatusAtivo.LIBERADO: "verde",
    StatusAtivo.AGUARDANDO: "amarelo",
    StatusAtivo.BARRADO_RISCO: "vermelho",
    StatusAtivo.BARRADO_AUDITOR: "vermelho",
    StatusAtivo.REJEITADO: "cinza",
    StatusAtivo.SEM_SETUP: "cinza",
    StatusAtivo.FILTRADO: "cinza",
    StatusAtivo.SEM_DADOS: "cinza",
    StatusAtivo.ERRO: "vermelho",
}


def _corta(texto: str, largura: int) -> str:
    return texto if len(texto) <= largura else texto[: largura - 1] + "…"


# ---------------------------------------------------------------------------
# tabela
# ---------------------------------------------------------------------------


def tabela(resultado: ResultadoScanner, ordenar_por: Optional[str] = None,
           cores: bool = False, limite: Optional[int] = None) -> str:
    """Ativo · Score · Setup · Direcao · Status · Timeframe · R:R · Risco · Timestamp."""
    linhas_ordenadas = resultado.ranking(ordenar_por, limite=limite)
    cabecalho = (
        f"  {'ATIVO':<7s} {'SCORE':>6s}  {'SETUP':<26s} {'DIR':<7s} "
        f"{'STATUS':<18s} {'TF':<5s} {'R:R':>5s} {'RISCO':>12s}  {'HORA':<6s}"
    )
    saida = [
        _c(f" SCANNER · {len(resultado.linhas)} ativo(s) · ordenado por "
           f"{ordenar_por or resultado.config.ordenar_por}", "negrito", ativo=cores),
        cabecalho,
        "  " + "─" * (LARGURA - 4),
    ]
    for l in linhas_ordenadas:
        saida.append(linha_da_tabela(l, cores))
    if not linhas_ordenadas:
        saida.append("  (nenhum ativo a mostrar com este filtro)")
    return "\n".join(saida)


def linha_da_tabela(l: LinhaScanner, cores: bool = False) -> str:
    direcao = l.direcao.value if l.direcao else "-"
    hora = f"{l.timestamp:%H:%M}" if l.timestamp else "-"
    risco = formata_dinheiro(l.risco_financeiro) if l.risco_financeiro else (
        formata_dinheiro(l.risco_por_acao) + "/ac" if l.risco_por_acao else "-"
    )
    return (
        f"  {l.symbol:<7s} {l.score:>6.1f}  {_corta(l.setup, 26):<26s} {direcao:<7s} "
        + _c(f"{l.status.value:<18s}", _COR_DO_STATUS[l.status], ativo=cores)
        + f" {l.timeframe:<5s} {l.rr:>5.2f} {risco:>12s}  {hora:<6s}"
    )


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def faixa_sem_oportunidade(cores: bool = False) -> str:
    """Nao ha oportunidade - e isso e' um resultado, nao um erro."""
    rotulo = "NENHUMA OPORTUNIDADE ENCONTRADA".center(LARGURA - 2)
    linhas = [
        "╔" + "═" * (LARGURA - 2) + "╗",
        "║" + rotulo + "║",
        "╚" + "═" * (LARGURA - 2) + "╝",
    ]
    return "\n".join(_c(l, "amarelo", "negrito", ativo=cores) for l in linhas)


def pagina(resultado: ResultadoScanner, ordenar_por: Optional[str] = None,
           cores: bool = False, limite: Optional[int] = None) -> str:
    """A tela do Scanner."""
    saida = [
        _c(f"SCANNER B3 · {resultado.instante:%d/%m/%Y %H:%M}", "negrito", ativo=cores),
        "─" * LARGURA,
    ]

    if not resultado.tem_oportunidades:
        saida.append(faixa_sem_oportunidade(cores))
        saida.append(f" {resultado.resumo}")
        saida.append(" varrer sem achar nada e' o resultado esperado na maior parte do pregao")
    else:
        saida.append(_c(f" {resultado.resumo}", "verde", "negrito", ativo=cores))
    saida.append("")
    saida.append(tabela(resultado, ordenar_por, cores, limite))

    filtrados = resultado.filtrados
    if filtrados:
        saida.append("")
        saida.append(_c(f" CORTADOS NOS FILTROS ({len(filtrados)})", "negrito", ativo=cores))
        for l in filtrados:
            saida.append(f"   {l.symbol:<7s} {l.motivo}")

    if resultado.avisos:
        saida.append("")
        saida.append(_c(" AVISOS", "negrito", ativo=cores))
        for aviso in dict.fromkeys(resultado.avisos):
            saida.append(f"   · {aviso}")
    return "\n".join(saida)


def detalhe(linha: LinhaScanner, cores: bool = False) -> str:
    """A trilha completa de um ativo: filtros e as oito etapas."""
    saida = [
        _c(f"{linha.symbol} · {linha.status.value}", "negrito", ativo=cores),
        f" {linha.motivo}",
        "",
        _c(" FILTROS INICIAIS", "negrito", ativo=cores),
    ]
    for f in linha.filtros:
        cor = "cinza" if not f.verificado else ("verde" if f.passou else "vermelho")
        saida.append(f"   {_c(f.simbolo, cor, ativo=cores)} {f.titulo:<20s} {f.detalhe}")

    saida.append("")
    saida.append(_c(" FLUXO", "negrito", ativo=cores))
    for e in linha.etapas:
        if not e.executada:
            saida.append(_c(f"   ·  {e.ordem}. {e.nome}: nao executada", "cinza", ativo=cores))
            continue
        cor = "verde" if e.passou else "vermelho"
        saida.append(f"   {_c(e.simbolo, cor, ativo=cores)}  {e.ordem}. {e.nome}: {e.detalhe}")

    if linha.auditoria is not None:
        from ..auditor.view import secao_auditor

        saida.append("")
        saida.append(secao_auditor(linha.auditoria, cores))
    return "\n".join(saida)
