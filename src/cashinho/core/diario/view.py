"""Pagina Diario: registros filtrados e as cinco visoes estatisticas.

A tela nao recomenda nada. Ela mostra o que aconteceu, agrupado de cinco
formas, e avisa quando a amostra e' pequena demais para significar alguma
coisa. A leitura e' sua.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .diario import DiarioDeTrades
from .estatisticas import AMOSTRA_MINIMA, Estatistica
from .modelos import Filtro, Registro
from ..ui import c as _c

LARGURA = 104

TITULOS = {
    "setup": "POR SETUP",
    "ativo": "POR ATIVO",
    "horario": "POR HORARIO DE ENTRADA",
    "dia": "POR DIA DA SEMANA",
    "timeframe": "POR TIMEFRAME",
}


def _valor(v: float, cores: bool = False) -> str:
    texto = f"{v:+,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    cor = "verde" if v > 0 else ("vermelho" if v < 0 else "cinza")
    return _c(f"R$ {texto}", cor, ativo=cores)


def _num(v: Optional[float], casas: int = 2) -> str:
    return "-" if v is None else f"{v:.{casas}f}".replace(".", ",")


def _corta(texto: str, largura: int) -> str:
    return texto if len(texto) <= largura else texto[: largura - 1] + "…"


# ---------------------------------------------------------------------------
# registros
# ---------------------------------------------------------------------------


def tabela_registros(registros: Sequence[Registro], cores: bool = False,
                     limite: Optional[int] = 30) -> str:
    mostrados = list(registros)[-limite:] if limite else list(registros)
    linhas = [_c(f" OPERACOES ({len(registros)})", "negrito", ativo=cores)]
    if not mostrados:
        linhas.append("   nenhuma operacao no recorte")
        return "\n".join(linhas)

    linhas.append(
        f"   {'DATA':<10s} {'HORA':<5s} {'ATIVO':<7s} {'DIR':<6s} {'SETUP':<22s} "
        f"{'SCORE':>5s} {'TF':<5s} {'QTD':>6s} {'ENTRADA':>8s} {'SAIDA':>8s} "
        f"{'R:R':>4s} {'RESULTADO':>13s} {'R':>6s}"
    )
    for r in mostrados:
        linhas.append(
            f"   {r.data:%d/%m/%Y} {r.aberta_em:%H:%M} {r.symbol:<7s} "
            f"{r.direcao.value[:5]:<6s} {_corta(r.setup, 22):<22s} {r.score:>5.0f} "
            f"{r.timeframe_setup:<5s} {r.quantidade:>6d} {r.entrada:>8.2f} {r.saida:>8.2f} "
            f"{r.rr:>4.1f} {_valor(r.resultado, cores):>13s} {r.resultado_em_r:>6.2f}"
        )
    if limite and len(registros) > limite:
        linhas.append(f"   ... e mais {len(registros) - limite} operacao(oes) antes destas")
    return "\n".join(linhas)


def detalhe_registro(r: Registro, cores: bool = False) -> str:
    """Uma operacao inteira - com os dois porques."""
    linhas = [
        _c(f"{r.symbol} · {r.direcao.value} · {r.data:%d/%m/%Y} {r.aberta_em:%H:%M}"
           f" -> {r.fechada_em:%H:%M}", "negrito", ativo=cores),
        f"   setup        {r.setup or '-'}   score {r.score:.0f}   timeframes {r.timeframes or '-'}",
        f"   entrada      {formata_dinheiro(r.entrada)}   stop {formata_dinheiro(r.stop)}"
        f"   alvo {formata_dinheiro(r.alvo)}   quantidade {r.quantidade}",
        f"   saida        {formata_dinheiro(r.saida)}   risco {formata_dinheiro(r.risco)}"
        f"   R:R {r.rr:.2f}   duracao {r.duracao_minutos:.0f} min",
        f"   resultado    {_valor(r.resultado, cores)}  ({r.resultado_em_r:+.2f} R,"
        f" custos {formata_dinheiro(r.custos)})",
    ]
    if r.motivo_entrada:
        linhas.append("")
        linhas.append(_c("   MOTIVO DA ENTRADA", "negrito", ativo=cores))
        for m in r.motivo_entrada:
            linhas.append(f"     · {m}")
    linhas.append("")
    linhas.append(_c("   MOTIVO DA SAIDA", "negrito", ativo=cores))
    linhas.append(f"     · {r.motivo_saida or '-'}")
    if r.condicoes_de_mercado:
        linhas.append("")
        linhas.append(_c("   CONDICOES DO MERCADO NA ENTRADA", "negrito", ativo=cores))
        for c in r.condicoes_de_mercado:
            linhas.append(f"     · {c}")
    if r.warnings_auditor:
        linhas.append("")
        linhas.append(_c("   AVISOS DO AUDITOR", "amarelo", "negrito", ativo=cores))
        for a in r.warnings_auditor:
            linhas.append(f"     ! {a}")
    if r.observacao:
        linhas.append("")
        linhas.append(f"   nota: {r.observacao}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# estatisticas
# ---------------------------------------------------------------------------


def tabela_estatisticas(estatisticas: Sequence[Estatistica], titulo: str,
                        cores: bool = False) -> str:
    linhas = [_c(f" {titulo}", "negrito", ativo=cores)]
    if not estatisticas:
        linhas.append("   sem dados")
        return "\n".join(linhas)

    linhas.append(
        f"   {'GRUPO':<24s} {'N':>4s} {'WIN':>6s} {'PAYOFF':>7s} {'PF':>6s} "
        f"{'EXPECT.':>12s} {'R MEDIO':>8s} {'TOTAL':>14s}"
    )
    for e in estatisticas:
        marca = " *" if e.amostra_pequena else "  "
        linhas.append(
            f"   {_corta(e.grupo, 24):<24s} {e.n_trades:>4d} {e.win_rate * 100:>5.0f}% "
            f"{_num(e.payoff):>7s} {_num(e.profit_factor):>6s} "
            f"{formata_dinheiro(e.expectancy):>12s} {e.r_medio:>+8.2f} "
            f"{_valor(e.resultado_total, cores):>14s}{marca}"
        )
    if any(e.amostra_pequena for e in estatisticas):
        linhas.append(
            _c(f"   * menos de {AMOSTRA_MINIMA} operacoes: numero pouco confiavel",
               "cinza", ativo=cores)
        )
    return "\n".join(linhas)


def painel_total(e: Estatistica, cores: bool = False) -> str:
    linhas = [_c(" RESUMO", "negrito", ativo=cores)]
    linhas.append(
        f"   {e.n_trades} operacao(oes)   {e.vencedores} ganho(s), {e.perdedores} perda(s)"
        f"   win rate {e.win_rate * 100:.0f}%"
    )
    linhas.append(
        f"   resultado {_valor(e.resultado_total, cores)}"
        f"   medio {formata_dinheiro(e.resultado_medio)}"
        f"   expectancy {formata_dinheiro(e.expectancy)}   R medio {e.r_medio:+.2f}"
    )
    linhas.append(
        f"   payoff {_num(e.payoff)}   profit factor {_num(e.profit_factor)}"
        f"   melhor {formata_dinheiro(e.melhor)}   pior {formata_dinheiro(e.pior)}"
        f"   custos {formata_dinheiro(e.custos)}"
    )
    if e.amostra_pequena and e.n_trades:
        linhas.append(_c(
            f"   amostra de {e.n_trades} operacao(oes): abaixo de {AMOSTRA_MINIMA} os numeros "
            "dizem pouco", "amarelo", ativo=cores))
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina(diario: DiarioDeTrades, filtro: Optional[Filtro] = None, cores: bool = False,
           limite: Optional[int] = 30, agrupamentos: Optional[Sequence[str]] = None) -> str:
    """A pagina Diario."""
    filtro = filtro or Filtro()
    registros = diario.filtrar(filtro)
    periodo = diario.periodo()

    cabecalho = "DIARIO DE TRADES"
    if periodo:
        cabecalho += f" · {periodo[0]:%d/%m/%Y} a {periodo[1]:%d/%m/%Y}"
    linhas = [_c(cabecalho, "negrito", ativo=cores), "─" * LARGURA]
    linhas.append(f" filtro: {filtro.descricao()}   ({len(registros)} de {len(diario)} operacoes)")

    if not registros:
        linhas.append("")
        linhas.append(_c(" nenhuma operacao neste recorte", "amarelo", ativo=cores))
        if len(diario):
            linhas.append(f"   o diario tem {len(diario)} operacao(oes) em outros recortes")
        return "\n".join(linhas)

    linhas.append("")
    linhas.append(painel_total(diario.estatistica(filtro), cores))
    linhas.append("")
    linhas.append(tabela_registros(registros, cores, limite))

    grupos = diario.agrupamentos(filtro)
    escolhidos = agrupamentos or list(grupos)
    for nome in escolhidos:
        if nome not in grupos:
            continue
        linhas.append("")
        linhas.append(tabela_estatisticas(grupos[nome], TITULOS.get(nome, nome.upper()), cores))

    linhas.append("")
    linhas.append(_c(
        " o diario mede, nao decide: os numeros sao contagem e media, sem nenhum ajuste "
        "automatico de estrategia", "cinza", ativo=cores))
    return "\n".join(linhas)


def resumo(diario: DiarioDeTrades, filtro: Optional[Filtro] = None) -> str:
    e = diario.estatistica(filtro)
    return (
        f"{e.n_trades} operacoes | win {e.win_rate * 100:.0f}% | "
        f"resultado {e.resultado_total:+.2f} | expectancy {e.expectancy:+.2f} | "
        f"R medio {e.r_medio:+.2f}"
    )
