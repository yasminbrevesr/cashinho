"""Tela Analise: o sinal, as justificativas e os fatores dos dois lados.

A tela nunca esconde o que pesou contra. Um sinal de compra com tres fatores
contrarios listados e' uma informacao melhor do que um "COMPRAR" sozinho na
tela - e e' assim que da para desconfiar da estrategia quando ela erra.
"""

from __future__ import annotations

from ...models import formata_dinheiro
from .models import Action, Signal

LARGURA = 68

_CORES = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
    "reset": "\033[0m",
}

_COR_DA_ACAO = {
    Action.BUY: "verde",
    Action.SELL: "vermelho",
    Action.WAIT: "amarelo",
    Action.NONE: "cinza",
}

AVISO_CURTO = "ESTRATEGIA DE VALIDACAO - NAO E' RECOMENDACAO"


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def barra_confianca(valor: float, largura: int = 10) -> str:
    cheias = int(round(max(0.0, min(1.0, valor)) * largura))
    return "█" * cheias + "·" * (largura - cheias)


def faixa_de_aviso(sinal: Signal, cores: bool = False) -> str:
    """Aviso de que a estrategia e' experimental - sempre no topo da tela."""
    if not sinal.experimental:
        return ""
    linha = f"⚠  {AVISO_CURTO}"
    return _c(linha, "amarelo", "negrito", ativo=cores)


def tela_analise(sinal: Signal, cores: bool = False) -> str:
    """A tela Analise de um ativo."""
    cor = _COR_DA_ACAO[sinal.action]
    linhas: list[str] = []

    cabecalho = (
        f"ANALISE · {sinal.symbol} · {sinal.timeframe} · "
        f"{sinal.timestamp.strftime('%d/%m %H:%M')}"
    )
    linhas.append(_c(cabecalho, "negrito", ativo=cores))
    linhas.append("─" * LARGURA)

    aviso = faixa_de_aviso(sinal, cores)
    if aviso:
        linhas.append(aviso)
        if sinal.aviso:
            linhas.append(_c(f"   {sinal.aviso}", "cinza", ativo=cores))
        linhas.append("")

    linhas.append(
        f" SINAL        {_c(sinal.action.value, cor, 'negrito', ativo=cores)}"
        f"   confianca {sinal.confidence:.0%}  [{barra_confianca(sinal.confidence)}]"
    )
    linhas.append(f"              {sinal.action.descricao}")
    linhas.append(f" SETUP        {sinal.setup}")
    linhas.append(f" ESTRATEGIA   {sinal.strategy}")

    linhas.append("")
    linhas.append(_c(" JUSTIFICATIVAS", "negrito", ativo=cores))
    if sinal.reasons:
        for razao in sinal.reasons:
            linhas.append(f"   · {razao}")
    else:
        linhas.append("   (nenhuma)")

    linhas.append("")
    linhas.append(_c(" FATORES FAVORAVEIS", "negrito", ativo=cores))
    linhas.extend(_bloco_fatores(sinal.favoraveis, "verde", cores, "nenhum fator a favor"))

    linhas.append("")
    linhas.append(_c(" FATORES CONTRARIOS", "negrito", ativo=cores))
    linhas.extend(_bloco_fatores(sinal.contrarios, "vermelho", cores, "nenhum fator contra"))

    if sinal.neutros:
        linhas.append("")
        linhas.append(_c(" FATORES NEUTROS", "negrito", ativo=cores))
        linhas.extend(_bloco_fatores(sinal.neutros, "cinza", cores, ""))

    if sinal.niveis:
        linhas.append("")
        linhas.append(_c(" NIVEIS DE REFERENCIA", "negrito", ativo=cores) + "  (nao sao ordens)")
        for rotulo, chave in (
            ("entrada", "entrada_referencia"),
            ("stop", "stop_referencia"),
            ("alvo", "alvo_referencia"),
            ("ATR", "atr"),
        ):
            if chave in sinal.niveis:
                linhas.append(f"   {rotulo:<9s} {formata_dinheiro(sinal.niveis[chave]):>12s}")

    secao_mtf = _secao_multitimeframe(sinal, cores)
    if secao_mtf:
        linhas.append("")
        linhas.append(secao_mtf)

    secao_score = _secao_score(sinal, cores)
    if secao_score:
        linhas.append("")
        linhas.append(secao_score)

    secao_auditoria = _secao_auditor(sinal, cores)
    if secao_auditoria:
        linhas.append("")
        linhas.append(secao_auditoria)

    linhas.append("")
    linhas.append(_c(" INVALIDACAO", "negrito", ativo=cores))
    linhas.append(f"   {sinal.invalidation}")
    return "\n".join(linhas)


def _secao_multitimeframe(sinal: Signal, cores: bool) -> str:
    """Renderiza a leitura multi-timeframe quando o sinal trouxer uma.

    O import e' local de proposito: a tela nao depende do modulo de
    confluencia, so sabe desenhar o que ele anexa.
    """
    leitura = sinal.extras.get("multitimeframe")
    if leitura is None:
        return ""
    from ..confluencia.view import secao_multitimeframe

    return secao_multitimeframe(leitura, sinal.extras.get("avaliacoes", ()), cores)


def _secao_score(sinal: Signal, cores: bool) -> str:
    """Abre o score da oportunidade quando o sinal trouxer uma."""
    oportunidade = sinal.extras.get("oportunidade")
    if oportunidade is None or getattr(oportunidade, "score_detalhado", None) is None:
        return ""
    from ..oportunidade.view import painel_score

    return painel_score(oportunidade.score_detalhado, cores)


def _secao_auditor(sinal: Signal, cores: bool) -> str:
    """Mostra o veredito do auditor quando o sinal trouxer um."""
    auditoria = sinal.extras.get("auditoria")
    if auditoria is None:
        return ""
    from ..auditor.view import secao_auditor

    return secao_auditor(auditoria, cores)


def _bloco_fatores(fatores, cor: str, cores: bool, vazio: str) -> list[str]:
    if not fatores:
        return [f"   {vazio}"] if vazio else []
    return [
        f"   {_c(f.simbolo, cor, ativo=cores)} {f.nome}"
        + (" (obrigatorio)" if f.obrigatorio else "")
        + f": {f.detalhe}"
        for f in fatores
    ]


def linha_de_lista(sinal: Signal, cores: bool = False) -> str:
    """Uma linha por ativo, para varrer a watchlist."""
    cor = _COR_DA_ACAO[sinal.action]
    faltando = ", ".join(f.nome for f in sinal.faltando)
    partes = [
        f"{sinal.symbol:<7s}",
        _c(f"{sinal.action.value:<4s}", cor, ativo=cores),
        f"{sinal.confidence:>4.0%}",
        sinal.setup,
    ]
    if faltando:
        partes.append(f"falta: {faltando}")
    return " | ".join(partes)
