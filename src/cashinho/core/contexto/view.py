"""A secao CONTEXTO DO MERCADO.

Regra desta tela: **nao ha celula em branco**. Todo instrumento aparece, e o
que nao tem numero mostra por que - indisponivel, atrasado ou sem fonte
confirmada. Esconder a linha faria o contexto parecer mais completo do que e'.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .modelos import (
    Correlacao,
    DirecaoDeMercado,
    EstadoDaLeitura,
    Leitura,
    MarketContext,
    NivelDeQualidade,
    NivelDeVolatilidade,
    RegimeDeMercado,
)

LARGURA = 72

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_COR_DO_REGIME = {
    RegimeDeMercado.RISCO_LIGADO: "verde",
    RegimeDeMercado.RISCO_DESLIGADO: "vermelho",
    RegimeDeMercado.ESTRESSE: "vermelho",
    RegimeDeMercado.LATERAL: "amarelo",
    RegimeDeMercado.CONFLITANTE: "amarelo",
    RegimeDeMercado.INDEFINIDO: "cinza",
}

_COR_DA_DIRECAO = {
    DirecaoDeMercado.ALTA: "verde",
    DirecaoDeMercado.BAIXA: "vermelho",
    DirecaoDeMercado.LATERAL: "amarelo",
    DirecaoDeMercado.INDISPONIVEL: "cinza",
}

_COR_DA_QUALIDADE = {
    NivelDeQualidade.BOA: "verde",
    NivelDeQualidade.PARCIAL: "amarelo",
    NivelDeQualidade.RUIM: "vermelho",
    NivelDeQualidade.SIMULADA: "amarelo",
    NivelDeQualidade.INDISPONIVEL: "cinza",
}

_COR_DA_VOLATILIDADE = {
    NivelDeVolatilidade.BAIXA: "cinza",
    NivelDeVolatilidade.NORMAL: "verde",
    NivelDeVolatilidade.ALTA: "amarelo",
    NivelDeVolatilidade.EXTREMA: "vermelho",
    NivelDeVolatilidade.INDISPONIVEL: "cinza",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    return "".join(_CORES[e] for e in estilos) + texto + _CORES["reset"]


def _numero(leitura: Leitura) -> str:
    if leitura.ultimo is None:
        return "-"
    casas = leitura.instrumento.casas
    if casas == 0:
        return f"{leitura.ultimo:,.0f}".replace(",", ".")
    return f"{leitura.ultimo:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _variacao(leitura: Leitura) -> str:
    if leitura.variacao_pct is None:
        return "-"
    return f"{leitura.variacao_pct:+.2f}%"


def linha_do_instrumento(leitura: Leitura, cores: bool = False) -> str:
    nome = leitura.instrumento.nome[:22]
    numero = _numero(leitura)
    variacao = _variacao(leitura)
    estado = leitura.estado.rotulo

    cor = {
        EstadoDaLeitura.OK: None,
        EstadoDaLeitura.ATRASADA: "amarelo",
        EstadoDaLeitura.INDISPONIVEL: "cinza",
        EstadoDaLeitura.SEM_FONTE: "amarelo",
        EstadoDaLeitura.SIMULADA: "amarelo",
    }[leitura.estado]

    texto_variacao = variacao
    if leitura.variacao_pct is not None and cores:
        estilo = "verde" if leitura.variacao_pct > 0 else (
            "vermelho" if leitura.variacao_pct < 0 else "cinza")
        texto_variacao = _c(f"{variacao:>9}", estilo, ativo=cores)
    else:
        texto_variacao = f"{variacao:>9}"

    marcado = _c(estado, cor, ativo=cores and cor is not None) if cor else estado
    return f"  {nome:<24}{numero:>12}{texto_variacao}   {marcado}"


def secao_correlacoes(correlacoes: Sequence[Correlacao], criterio: str = "") -> str:
    if not correlacoes:
        # a lista vazia tem duas causas - nenhum par forte o bastante, ou
        # amostra curta demais para calcular - e a mensagem nao pode escolher
        # uma delas por conta propria
        detalhe = f" ({criterio})" if criterio else ""
        return ("  CORRELACOES RELEVANTES\n"
                f"    nenhum par atingiu o criterio{detalhe}")
    linhas = [f"  CORRELACOES RELEVANTES (janela {correlacoes[0].janela})"]
    for c in correlacoes:
        par = f"{c.a} x {c.b}"
        linhas.append(f"    {par:<40}{c.valor:+.2f}  {c.forca:<9}{c.amostra} pontos")
    return "\n".join(linhas)


def secao_contexto(contexto: Optional[MarketContext], cores: bool = False) -> str:
    """A secao CONTEXTO DO MERCADO, para embutir em qualquer tela."""
    titulo = _c(" CONTEXTO DO MERCADO", "negrito", ativo=cores)
    if contexto is None:
        return f"{titulo}\n   contexto nao carregado"

    q = contexto.data_quality
    linhas = [
        f"{titulo}{contexto.timestamp.strftime('%d/%m %H:%M'):>{max(LARGURA - 21, 1)}}",
        "  " + "─" * (LARGURA - 4),
        f"  {'REGIME':<16}{_c(contexto.market_regime.rotulo, _COR_DO_REGIME[contexto.market_regime], ativo=cores)}",
        f"  {'':<16}{contexto.market_regime.descricao}",
        f"  {'IBOVESPA':<16}{_c(contexto.ibovespa_direction.rotulo, _COR_DA_DIRECAO[contexto.ibovespa_direction], ativo=cores)}",
        f"  {'VOLATILIDADE':<16}{_c(contexto.volatility.rotulo, _COR_DA_VOLATILIDADE[contexto.volatility], ativo=cores)}",
        f"  {'QUALIDADE':<16}{_c(q.nivel.rotulo, _COR_DA_QUALIDADE[q.nivel], ativo=cores)}  {q.resumo}",
        "",
        f"  {'INSTRUMENTO':<24}{'ULTIMO':>12}{'DIA':>9}   ESTADO",
    ]
    linhas.extend(linha_do_instrumento(l, cores) for l in contexto.leituras)
    linhas.append("")
    linhas.append(secao_correlacoes(contexto.relevant_correlations,
                                    contexto.criterio_correlacao))

    if q.notas:
        linhas.append("")
        for nota in q.notas:
            linhas.append(f"  ! {nota}")
    if contexto.notas:
        linhas.append("")
        linhas.append("  LEITURA")
        for nota in contexto.notas:
            linhas.append(f"    · {nota}")

    linhas.append("")
    linhas.append(_c(
        "  este contexto NAO gera operacao: ele so pesa a favor ou contra uma\n"
        "  leitura que ja existe", "cinza", ativo=cores))
    return "\n".join(linhas)


def pagina(contexto: MarketContext, cores: bool = False) -> str:
    """A tela completa do contexto."""
    return "\n".join(["", secao_contexto(contexto, cores), ""])
