"""Tela BOLETA GENIAL - feita para ser digitada, nao enviada.

Duas decisoes de layout que vieram do objetivo:

- os campos aparecem em bloco alinhado, um por linha, no formato
  ``Campo: valor`` - da para bater o olho e digitar sem procurar;
- todo campo cujo comportamento na Genial nao foi confirmado leva um ``⚠``
  na frente, e a tela termina com a lista do que precisa ser conferido.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .modelos import Boleta, PapelDaBoleta, ResumoOperacao, Ticket
from .regras import Regra

LARGURA = 76

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

SELO = "REGRA GENIAL A CONFIRMAR"


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


# ---------------------------------------------------------------------------
# avisos
# ---------------------------------------------------------------------------


def faixa_nao_envia(cores: bool = False) -> str:
    """O aviso que nao pode faltar: nada aqui vai para a corretora."""
    rotulo = "ESTA TELA NAO ENVIA ORDEM - DIGITACAO MANUAL".center(LARGURA - 2)
    linhas = [
        "╔" + "═" * (LARGURA - 2) + "╗",
        "║" + rotulo + "║",
        "╚" + "═" * (LARGURA - 2) + "╝",
    ]
    return "\n".join(_c(l, "amarelo", "negrito", ativo=cores) for l in linhas)


# ---------------------------------------------------------------------------
# blocos
# ---------------------------------------------------------------------------


def painel_resumo(r: ResumoOperacao, cores: bool = False) -> str:
    """Os numeros da operacao que acompanham a boleta."""
    direcao = r.direcao.value if r.direcao else "-"
    linhas = [_c(" OPERACAO", "negrito", ativo=cores)]
    linhas.append(f"   ativo        {r.ativo:<12s} direcao   {direcao}")
    linhas.append(
        f"   entrada      {formata_dinheiro(r.entrada):>12s}"
        f"   stop  {formata_dinheiro(r.stop):>12s}"
        f"   alvo  {formata_dinheiro(r.alvo):>12s}"
    )
    linhas.append(
        f"   risco        {formata_dinheiro(r.risco_monetario):>12s}"
        f"   retorno potencial {formata_dinheiro(r.retorno_potencial):>12s}"
        f"   R:R {r.rr:.2f}"
    )
    linhas.append(
        f"   score        {r.score:>12.1f}   status {r.status}"
    )
    linhas.append(f"   setup        {r.setup}")
    linhas.append(f"   timestamp    {r.timestamp:%d/%m/%Y %H:%M}")
    return "\n".join(linhas)


def bloco_boleta(b: Boleta, cores: bool = False, mostrar_observacoes: bool = True) -> str:
    """Uma boleta com os campos alinhados para digitacao."""
    titulo = f" BOLETA {b.tipo.value.upper()}  ·  {b.papel.value}"
    linhas = [_c(titulo, "negrito", ativo=cores)]
    if b.explicacao:
        linhas.append(_c(f"   {b.explicacao}", "cinza", ativo=cores))
    largura = max((len(c.rotulo) for c in b.campos), default=10)

    for campo in b.campos:
        marca = _c("⚠", "amarelo", ativo=cores) if not campo.confirmado else " "
        linhas.append(f"   {marca} {campo.rotulo:<{largura}s} : {campo.valor}")
        if mostrar_observacoes and campo.observacao:
            linhas.append(f"     {'':<{largura}s}   {_c(campo.observacao, 'cinza', ativo=cores)}")
    return "\n".join(linhas)


def bloco_para_copiar(ticket: Ticket) -> str:
    """So os campos, sem decoracao - o bloco que se copia e digita."""
    if not ticket.gerado:
        return ""
    partes = []
    for b in ticket.boletas:
        partes.append(f"[{b.tipo.value}] {b.papel.value}")
        partes.append(b.para_copiar())
        partes.append("")
    return "\n".join(partes).rstrip()


def secao_condicoes(ticket: Ticket, cores: bool = False) -> str:
    """ENTRAR SOMENTE SE / CANCELAR A OPERACAO SE - obrigatorias."""
    linhas = [_c(" ENTRAR SOMENTE SE:", "verde", "negrito", ativo=cores)]
    for c in ticket.entrar_somente_se:
        linhas.append(f"   · {c}")
    if not ticket.entrar_somente_se:
        linhas.append("   (nenhuma condicao registrada)")

    linhas.append("")
    linhas.append(_c(" CANCELAR A OPERACAO SE:", "vermelho", "negrito", ativo=cores))
    for c in ticket.cancelar_se:
        linhas.append(f"   · {c}")
    if not ticket.cancelar_se:
        linhas.append("   (nenhuma condicao registrada)")
    return "\n".join(linhas)


def secao_pendencias(pendencias: Sequence[Regra], cores: bool = False) -> str:
    """O que ainda depende da documentacao da Genial."""
    pendentes = [r for r in pendencias if r.pendente]
    if not pendentes:
        return ""
    linhas = [
        _c(f" {SELO} ({len(pendentes)})", "amarelo", "negrito", ativo=cores),
        _c("   nada disto foi verificado contra a documentacao da Genial", "cinza", ativo=cores),
        "",
    ]
    for r in pendentes:
        linhas.append(f"   ⚠ {_c(r.titulo, 'amarelo', ativo=cores)}")
        linhas.append(f"     assumido:  {r.assumido}")
        if r.confirmar:
            linhas.append(f"     confirmar: {r.confirmar}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina(ticket: Ticket, cores: bool = False, mostrar_observacoes: bool = True) -> str:
    """A tela BOLETA GENIAL inteira."""
    linhas = [
        _c("BOLETA GENIAL", "negrito", ativo=cores),
        "─" * LARGURA,
        faixa_nao_envia(cores),
        "",
    ]

    if not ticket.gerado:
        linhas.append(_c(" BOLETA NAO GERADA", "vermelho", "negrito", ativo=cores))
        linhas.append(f"   {ticket.motivo}")
        pendencias = secao_pendencias(ticket.pendencias, cores)
        if pendencias:
            linhas.append("")
            linhas.append(pendencias)
        return "\n".join(linhas)

    linhas.append(painel_resumo(ticket.resumo, cores))
    for b in ticket.boletas:
        linhas.append("")
        linhas.append(bloco_boleta(b, cores, mostrar_observacoes))

    linhas.append("")
    linhas.append(secao_condicoes(ticket, cores))

    if ticket.avisos:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for a in ticket.avisos:
            linhas.append(f"   · {a}")

    pendencias = secao_pendencias(ticket.pendencias, cores)
    if pendencias:
        linhas.append("")
        linhas.append(pendencias)
    return "\n".join(linhas)


def resumo_uma_linha(ticket: Ticket) -> str:
    if not ticket.gerado:
        return f"boleta nao gerada: {ticket.motivo}"
    r = ticket.resumo
    tipos = " + ".join(b.tipo.value for b in ticket.boletas)
    return (
        f"{r.ativo} {r.direcao.value if r.direcao else '-'} {r.quantidade} @ "
        f"{formata_dinheiro(r.entrada)} | stop {formata_dinheiro(r.stop)} | "
        f"alvo {formata_dinheiro(r.alvo)} | R:R {r.rr:.2f} | {tipos}"
    )
