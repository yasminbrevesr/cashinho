"""Tela da oportunidade: estado, score aberto componente a componente, niveis.

A regra desta tela: **nenhum numero sem a conta que o gerou**. O score final
aparece sempre acompanhado das onze notas, com peso e contribuicao, e da
frase que justifica cada uma. Se o score for 84, da para apontar de onde
vieram os 84 - e o que puxou para baixo.
"""

from __future__ import annotations

from typing import Optional

from ...models import formata_dinheiro
from .estados import EstadoOportunidade
from .modelos import Opportunity
from .score import ScoreDetalhado

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
    EstadoOportunidade.APROVADO: "verde",
    EstadoOportunidade.AGUARDANDO_GATILHO: "amarelo",
    EstadoOportunidade.REJEITADO: "vermelho",
    EstadoOportunidade.NAO_OPERAR: "cinza",
    EstadoOportunidade.EXPIRADO: "cinza",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def barra(nota: float, largura: int = 10) -> str:
    cheias = int(round(max(0.0, min(100.0, nota)) / 100.0 * largura))
    return "█" * cheias + "·" * (largura - cheias)


def _cor_da_nota(nota: float) -> str:
    if nota >= 70:
        return "verde"
    if nota >= 45:
        return "amarelo"
    return "vermelho"


# ---------------------------------------------------------------------------
# estado
# ---------------------------------------------------------------------------


def faixa_de_estado(op: Opportunity, agora=None, cores: bool = False) -> str:
    """A faixa que responde, sem rodeio, o que fazer com esta oportunidade."""
    estado = op.estado_em(agora) if agora else op.estado
    rotulo = estado.value.center(LARGURA - 2)
    estilo = (_COR_DO_ESTADO[estado], "negrito")
    linhas = [
        "╔" + "═" * (LARGURA - 2) + "╗",
        "║" + rotulo + "║",
        "╚" + "═" * (LARGURA - 2) + "╝",
    ]
    return "\n".join(_c(l, *estilo, ativo=cores) for l in linhas)


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def painel_score(detalhado: ScoreDetalhado, cores: bool = False, mostrar_peso: bool = True) -> str:
    """As onze notas, o peso de cada uma e o score final."""
    if detalhado is None:
        return ""
    soma = detalhado.soma_dos_pesos
    linhas = [_c(" SCORE", "negrito", ativo=cores)]
    for c in detalhado.por_contribuicao():
        cor = _cor_da_nota(c.nota)
        linha = f"   {c.nome:<21s} {_c(barra(c.nota), cor, ativo=cores)} {c.nota:>5.0f}"
        if mostrar_peso:
            linha += f"   peso {c.peso:.1f}  contribui {c.contribuicao(soma):>5.1f}"
        linhas.append(linha)
        linhas.append(f"   {'':<21s} └ {c.leitura}")
    linhas.append("   " + "─" * (LARGURA - 6))
    total = detalhado.total
    linhas.append(
        f"   {'SCORE FINAL':<21s} {_c(barra(total), _cor_da_nota(total), ativo=cores)} "
        + _c(f"{total:>5.0f}", _cor_da_nota(total), "negrito", ativo=cores)
    )
    return "\n".join(linhas)


def resumo_score(detalhado: ScoreDetalhado) -> str:
    """Uma linha: ``Tendencia 90 · Volume 78 · ... · FINAL 84``."""
    if detalhado is None:
        return ""
    partes = [f"{c.nome} {c.nota:.0f}" for c in detalhado.por_contribuicao()[:4]]
    return " · ".join(partes) + f" · FINAL {detalhado.total:.0f}"


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina_oportunidade(op: Opportunity, agora=None, cores: bool = False) -> str:
    """A tela completa de uma oportunidade."""
    estado = op.estado_em(agora) if agora else op.estado
    linhas = [
        _c(f"OPORTUNIDADE · {op.symbol} · {op.timestamp:%d/%m %H:%M}", "negrito", ativo=cores),
        "─" * LARGURA,
        faixa_de_estado(op, agora, cores),
        f" {estado.descricao}",
    ]
    if op.motivo_do_estado:
        linhas.append(f" {_c(op.motivo_do_estado, _COR_DO_ESTADO[estado], ativo=cores)}")

    if estado is EstadoOportunidade.EXPIRADO and op.expires_at:
        linhas.append(f" a janela terminou as {op.expires_at:%H:%M}")

    linhas.append("")
    linhas.append(_c(" OPERACAO", "negrito", ativo=cores))
    direcao = op.direction.value if op.direction else "-"
    linhas.append(f"   direcao      {direcao}")
    linhas.append(f"   setup        {op.setup}")
    if op.entry:
        linhas.append(
            f"   entrada      {formata_dinheiro(op.entry)}"
            f"      stop {formata_dinheiro(op.stop)}"
            f"      alvo {formata_dinheiro(op.target)}"
        )
        linhas.append(
            f"   risco/retorno {op.risk_reward:.2f}"
            f"      risco por acao {formata_dinheiro(op.risco_por_acao)}"
        )
    if op.expires_at:
        validade = op.validade_minutos()
        linhas.append(f"   validade     ate {op.expires_at:%H:%M}"
                      + (f" ({validade:.0f} min)" if validade else ""))

    linhas.append("")
    linhas.append(_c(" TIMEFRAMES", "negrito", ativo=cores))
    linhas.append(
        f"   contexto {op.timeframe_context} · tendencia {op.timeframe_trend} · "
        f"setup {op.timeframe_setup} · gatilho {op.timeframe_trigger}"
    )

    if op.score_detalhado is not None:
        linhas.append("")
        linhas.append(painel_score(op.score_detalhado, cores))

    linhas.append("")
    linhas.append(_c(" MOTIVOS", "negrito", ativo=cores))
    for r in op.reasons:
        linhas.append(f"   · {r}")

    if op.warnings:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for a in op.warnings:
            linhas.append("   " + _c(f"! {a}", "amarelo", ativo=cores))

    linhas.append("")
    linhas.append(_c(" INVALIDACAO", "negrito", ativo=cores))
    linhas.append(f"   {op.invalidation}")
    return "\n".join(linhas)


def linha_de_lista(op: Opportunity, agora=None, cores: bool = False) -> str:
    """Uma linha por ativo, para varrer varias oportunidades."""
    estado = op.estado_em(agora) if agora else op.estado
    direcao = op.direction.value if op.direction else "-"
    partes = [
        f"{op.symbol:<7s}",
        _c(f"{estado.value:<18s}", _COR_DO_ESTADO[estado], ativo=cores),
        f"{direcao:<6s}",
        f"score {op.score:>5.1f}",
        f"RR {op.risk_reward:>4.2f}",
        op.setup[:38],
    ]
    return " | ".join(partes)
