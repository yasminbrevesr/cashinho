"""A secao NOTICIAS E EVENTOS.

Quando a fonte nao esta confiavel ou atualizada, a secao mostra
**NOTICIAS INDISPONIVEIS** e diz por que. Nao ha estado intermediario em que a
tela fica em branco: branco seria lido como "nao ha evento", que e' uma
afirmacao que este modulo, sem agenda, nao pode fazer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from .modelos import AgendaDeEventos, Evento
from .politica import AvaliacaoDeEventos
from .tipos import Disponibilidade, Severidade, ViesDirecional

LARGURA = 72

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_COR_DA_SEVERIDADE = {
    Severidade.CRITICA: "vermelho",
    Severidade.ALTA: "vermelho",
    Severidade.MEDIA: "amarelo",
    Severidade.BAIXA: "cinza",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def _quando(evento: Evento, instante: Optional[datetime]) -> str:
    if instante is None:
        return evento.timestamp.strftime("%d/%m %H:%M")
    faltam = evento.minutos_ate(instante)
    if abs(faltam) < 60:
        return f"em {faltam:.0f} min" if faltam >= 0 else f"ha {abs(faltam):.0f} min"
    if 0 <= faltam < 48 * 60:
        return f"em {faltam / 60:.0f}h ({evento.timestamp:%d/%m %H:%M})"
    # longe demais para contar em horas: a data ja diz tudo
    return f"{evento.timestamp:%d/%m %H:%M}"


def linha_do_evento(evento: Evento, instante: Optional[datetime] = None,
                    cores: bool = False) -> str:
    severidade = _c(evento.severity.rotulo, _COR_DA_SEVERIDADE[evento.severity],
                    ativo=cores)
    vies = evento.directional_bias.rotulo
    marca = "" if evento.confirmado else "  (data a confirmar)"
    quando = _quando(evento, instante)
    linha = (f"    {evento.event_type.curto:<15}{evento.alvo:<8}"
             f"{quando:<21} {severidade:<10} {vies}")
    if evento.titulo:
        linha += f"\n    {'':<15}└ {evento.titulo}"
    return linha + marca


def cabecalho_disponibilidade(agenda: AgendaDeEventos, cores: bool = False) -> str:
    if agenda.confiavel:
        rotulo = _c(agenda.rotulo, "verde", ativo=cores)
        fonte = f"fonte {agenda.fonte}" if agenda.fonte else ""
        atualizado = (f"atualizada {agenda.atualizado_em:%d/%m %H:%M}"
                      if agenda.atualizado_em else "")
        return f"  {rotulo}   " + " · ".join(p for p in (fonte, atualizado) if p)
    detalhe = agenda.motivo or agenda.disponibilidade.detalhe
    return f"  {_c(agenda.rotulo, 'vermelho', 'negrito', ativo=cores)}   {detalhe}"


def secao_noticias(agenda: Optional[AgendaDeEventos], instante: Optional[datetime] = None,
                   symbol: str = "", cores: bool = False,
                   avaliacao: Optional[AvaliacaoDeEventos] = None) -> str:
    """A secao NOTICIAS E EVENTOS, para embutir em qualquer tela."""
    titulo = _c(" NOTICIAS E EVENTOS", "negrito", ativo=cores)
    if agenda is None:
        return (f"{titulo}\n  "
                + _c(Disponibilidade.SEM_FONTE.rotulo, "vermelho", "negrito", ativo=cores)
                + "   nenhuma agenda carregada")

    linhas = [titulo, cabecalho_disponibilidade(agenda, cores)]

    eventos = agenda.para(symbol) if symbol else agenda.eventos
    if not eventos:
        if agenda.confiavel:
            linhas.append("    nenhum evento na agenda para este ativo")
        else:
            linhas.append("    sem agenda nao da para saber se ha evento a vista")
    else:
        linhas.append("")
        linhas.append(f"    {'TIPO':<15}{'ALVO':<8}{'QUANDO':<22}{'SEVERIDADE':<10} VIES")
        for e in eventos[:8]:
            linhas.append(linha_do_evento(e, instante, cores))

    if avaliacao is not None and avaliacao.pesou:
        linhas.append("")
        linhas.append(_c("  EFEITO NA OPERACAO", "negrito", ativo=cores))
        if avaliacao.bloqueado:
            linhas.append("    " + _c("OPERACAO BLOQUEADA", "vermelho", "negrito", ativo=cores)
                          + f"  {avaliacao.motivo}")
        if avaliacao.ajuste_de_score:
            linhas.append(f"    score          {avaliacao.ajuste_de_score:+.0f} pontos")
        if avaliacao.multiplicador_de_risco > 1:
            linhas.append(
                f"    risco          posicao dividida por "
                f"{avaliacao.multiplicador_de_risco:.2f}")

    if avaliacao is not None and avaliacao.avisos:
        linhas.append("")
        for aviso in avaliacao.avisos:
            linhas.append("    " + _c(f"! {aviso}", "amarelo", ativo=cores))

    if agenda.descartados:
        linhas.append("")
        linhas.append(f"  {len(agenda.descartados)} registro(s) descartado(s) - "
                      "nao viraram evento:")
        for d in agenda.descartados[:3]:
            linhas.append(f"    · {d}")

    linhas.append("")
    linhas.append(_c(
        "  uma notícia nunca gera compra ou venda: ela so desconta score,\n"
        "  reduz posicao ou bloqueia a operacao", "cinza", ativo=cores))
    return "\n".join(linhas)


def pagina(agenda: AgendaDeEventos, instante: Optional[datetime] = None,
           symbol: str = "", cores: bool = False,
           avaliacao: Optional[AvaliacaoDeEventos] = None) -> str:
    return "\n".join(["", secao_noticias(agenda, instante, symbol, cores, avaliacao), ""])
