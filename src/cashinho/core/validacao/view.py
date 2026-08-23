"""Tela de validacao: as tres particoes lado a lado e os alertas."""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .cofre import CofreDeTeste
from .divisao import DivisaoDeDados, Particao
from .relatorio import Alerta, Medidas, RelatorioDeValidacao, Severidade
from .selecao import Selecao
from .walkforward import ResultadoWalkForward

LARGURA = 86

_CORES = {
    "verde": "\033[32m", "vermelho": "\033[31m", "amarelo": "\033[33m",
    "cinza": "\033[90m", "negrito": "\033[1m", "reset": "\033[0m",
}

_COR_DA_PARTICAO = {
    Particao.TRAIN: "cinza", Particao.VALIDATION: "amarelo", Particao.TEST: "negrito",
}


def _c(texto: str, *estilos: str, ativo: bool = True) -> str:
    if not ativo:
        return texto
    prefixo = "".join(_CORES[e] for e in estilos if e in _CORES)
    return f"{prefixo}{texto}{_CORES['reset']}" if prefixo else texto


def _num(v: Optional[float], casas: int = 2, sufixo: str = "") -> str:
    if v is None:
        return "-"
    return f"{v:.{casas}f}{sufixo}".replace(".", ",")


# ---------------------------------------------------------------------------


def tabela_particoes(relatorio: RelatorioDeValidacao, cores: bool = False) -> str:
    """As seis medidas nas tres particoes."""
    linhas = [_c(" COMPARACAO", "negrito", ativo=cores)]
    linhas.append(
        f"   {'PARTICAO':<12s} {'DIAS':>5s} {'TRADES':>7s} {'RETORNO':>10s} "
        f"{'DRAWDOWN':>10s} {'PF':>7s} {'SHARPE':>8s} {'EXPECTANCY':>12s}"
    )
    linhas.append("   " + "─" * (LARGURA - 6))
    for particao in (Particao.TRAIN, Particao.VALIDATION, Particao.TEST):
        m = relatorio.medida(particao)
        if m is None:
            linhas.append(f"   {particao.rotulo:<12s} {'(nao medida)':>44s}")
            continue
        cor = "verde" if m.retorno_pct > 0 else ("vermelho" if m.retorno_pct < 0 else "cinza")
        linhas.append(
            f"   {_c(f'{particao.rotulo:<12s}', _COR_DA_PARTICAO[particao], ativo=cores)} "
            f"{m.dias:>5d} {m.n_trades:>7d} "
            f"{_c(f'{m.retorno_pct:>+9.2f}%', cor, ativo=cores)} "
            f"{_num(m.max_drawdown_pct, 2, '%'):>10s} {_num(m.profit_factor):>7s} "
            f"{_num(m.sharpe):>8s} {formata_dinheiro(m.expectancy):>12s}"
        )
    return "\n".join(linhas)


def secao_alertas(alertas: Sequence[Alerta], cores: bool = False) -> str:
    linhas = [_c(" ALERTAS DE DEGRADACAO", "negrito", ativo=cores)]
    if not alertas:
        linhas.append("   nenhum sinal de degradacao nas medidas comparadas")
        return "\n".join(linhas)

    for a in alertas:
        cor = {"critico": "vermelho", "alerta": "amarelo", "observacao": "cinza"}[
            a.severidade.value]
        linhas.append(
            f"   {_c(a.severidade.simbolo, cor, ativo=cores)} "
            f"[{a.particao.rotulo}] {a.mensagem}"
        )
    return "\n".join(linhas)


def secao_cofre(cofre: Optional[CofreDeTeste], cores: bool = False) -> str:
    if cofre is None:
        return ""
    linhas = [_c(" COFRE DO TEST", "negrito", ativo=cores)]
    meta = cofre.espiar_metadados()
    linhas.append(f"   periodo {meta['inicio']} a {meta['fim']} · {meta['dias']} pregoes")
    if not cofre.foi_aberto:
        linhas.append(_c("   fechado - o TEST nao foi consultado nesta rodada",
                         "verde", ativo=cores))
        return "\n".join(linhas)

    cor = "vermelho" if cofre.contaminado else "amarelo"
    linhas.append(_c(f"   aberto {cofre.vezes} vez(es)", cor, ativo=cores))
    for a in cofre.aberturas:
        linhas.append(f"     {a.quando:%d/%m %H:%M}  {a.motivo}")
    if cofre.contaminado:
        linhas.append(_c(
            "   a partir da segunda abertura o TEST deixa de ser out-of-sample",
            "vermelho", ativo=cores))
    return "\n".join(linhas)


def secao_selecao(selecao: Optional[Selecao], cores: bool = False) -> str:
    if selecao is None:
        return ""
    linhas = [_c(" SELECAO DE PARAMETROS", "negrito", ativo=cores)]
    linhas.append(_c("   medida em TRAIN, escolhida em VALIDATION, nunca no TEST",
                     "cinza", ativo=cores))
    linhas.append(
        f"   {'CANDIDATO':<24s} {'TREINO':>18s} {'VALIDACAO':>18s}"
    )
    for treino in selecao.em_treino:
        validacao = selecao.medida(treino.candidato, Particao.VALIDATION)
        escolhido = (selecao.escolhido is not None
                     and selecao.escolhido.nome == treino.candidato)
        marca = " ◀ escolhido" if escolhido else ""
        linhas.append(
            f"   {treino.candidato[:24]:<24s} "
            f"{treino.retorno_pct:>+9.2f}% ({treino.n_trades:>3d}) "
            f"{(validacao.retorno_pct if validacao else 0):>+9.2f}% "
            f"({validacao.n_trades if validacao else 0:>3d}){marca}"
        )
    if selecao.descartados:
        linhas.append("   descartados:")
        for nome, motivo in selecao.descartados:
            linhas.append(f"     · {nome}: {motivo}")
    linhas.append(f"   {selecao.motivo}")
    return "\n".join(linhas)


def pagina(relatorio: RelatorioDeValidacao, cores: bool = False) -> str:
    """A tela de validacao."""
    d = relatorio.divisao
    linhas = [
        _c(f"VALIDACAO · {d.serie.symbol} · {d.serie.timeframe}", "negrito", ativo=cores),
        "─" * LARGURA,
        f" {d.resumo()}",
    ]
    if relatorio.candidato:
        linhas.append(f" configuracao: {relatorio.candidato}")

    if not relatorio.medidas:
        linhas.append("")
        linhas.append(_c(" NENHUMA CONFIGURACAO APROVADA", "vermelho", "negrito", ativo=cores))
        if relatorio.selecao:
            linhas.append(f"   {relatorio.selecao.motivo}")
            linhas.append("")
            linhas.append(secao_selecao(relatorio.selecao, cores))
        return "\n".join(linhas)

    linhas.append("")
    linhas.append(tabela_particoes(relatorio, cores))

    selecao = secao_selecao(relatorio.selecao, cores)
    if selecao:
        linhas.append("")
        linhas.append(selecao)

    linhas.append("")
    linhas.append(secao_alertas(relatorio.alertas, cores))

    cofre = secao_cofre(relatorio.cofre, cores)
    if cofre:
        linhas.append("")
        linhas.append(cofre)

    linhas.append("")
    cor = "vermelho" if relatorio.degradou else "verde"
    linhas.append(_c(" VEREDITO", "negrito", ativo=cores))
    linhas.append("   " + _c(relatorio.veredito, cor, ativo=cores))
    linhas.append(_c(
        "   validacao nao prova que funciona: ela mostra quando NAO funciona fora "
        "do periodo ajustado", "cinza", ativo=cores))
    return "\n".join(linhas)


# ---------------------------------------------------------------------------


def pagina_walk_forward(resultado: ResultadoWalkForward, cores: bool = False) -> str:
    """A tela do walk-forward."""
    linhas = [_c("WALK-FORWARD", "negrito", ativo=cores), "─" * LARGURA]
    if not resultado.ciclos:
        linhas.append(_c(f" {resultado.veredito}", "amarelo", ativo=cores))
        for aviso in resultado.avisos:
            linhas.append(f"   · {aviso}")
        return "\n".join(linhas)

    linhas.append(
        f"   {'CICLO':<6s} {'TREINO':<24s} {'FORA DA AMOSTRA':<24s} "
        f"{'RETORNO':>10s} {'TRADES':>7s}"
    )
    linhas.append("   " + "─" * (LARGURA - 6))
    for c in resultado.ciclos:
        cor = "verde" if c.sustentou else "vermelho"
        marca = "✔" if c.sustentou else "✖"
        linhas.append(
            f"   {c.indice:<6d} "
            f"{f'{c.treino.inicio:%d/%m}-{c.treino.fim:%d/%m} ({c.medida_treino.retorno_pct:+.1f}%)':<24s} "
            f"{f'{c.teste.inicio:%d/%m}-{c.teste.fim:%d/%m}':<24s} "
            + _c(f"{c.medida_teste.retorno_pct:>+9.2f}%", cor, ativo=cores)
            + f" {c.medida_teste.n_trades:>7d}  {_c(marca, cor, ativo=cores)}"
        )

    linhas.append("")
    linhas.append(_c(" CONSISTENCIA", "negrito", ativo=cores))
    cor = "verde" if resultado.consistencia >= 0.6 else "vermelho"
    linhas.append(
        f"   {resultado.sustentaram}/{resultado.total} ciclos "
        + _c(f"({resultado.consistencia:.0%})", cor, ativo=cores)
        + f"   retorno medio fora {resultado.retorno_medio_fora:+.2f}%"
        f"   {resultado.trades_fora} trades"
    )
    linhas.append("   " + _c(resultado.veredito, cor, ativo=cores))

    if resultado.avisos:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for aviso in dict.fromkeys(resultado.avisos):
            linhas.append(f"   · {aviso}")
    return "\n".join(linhas)
