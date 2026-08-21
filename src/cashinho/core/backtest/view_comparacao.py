"""Tela Comparar Timeframes: tabela, graficos e o veredito.

Escolha das formas (e do que NAO usar):

- a **tabela** e' a forma principal: sao oito metricas por timeframe, e
  nenhum grafico mostra oito grandezas ao mesmo tempo sem virar enfeite;
- **barras** para as magnitudes (retorno, drawdown, nota), com o valor
  escrito na ponta - em terminal nao existe tooltip para carregar o numero;
- **dispersao risco x retorno** para a comparacao que interessa. Dois eixos y
  no mesmo grafico (retorno de um lado, drawdown do outro) seria a forma mais
  facil de enganar quem le: aqui cada eixo tem uma grandeza so;
- **destaque**, nao arco-iris: o timeframe recomendado aparece marcado e o
  resto fica discreto.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from ...models import formata_dinheiro
from .comparacao import ComparacaoTimeframes, LinhaComparacao, StatusTimeframe

LARGURA = 96

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


def _num(valor: Optional[float], casas: int = 2, sufixo: str = "", sinal: bool = False) -> str:
    if valor is None:
        return "-"
    formato = f"{{:{'+' if sinal else ''}.{casas}f}}"
    return (formato.format(valor) + sufixo).replace(".", ",")


def _situacao(linha: LinhaComparacao, recomendado: Optional[LinhaComparacao]) -> str:
    if linha.status is StatusTimeframe.NAO_APLICAVEL:
        return "n/a"
    if linha.status is StatusTimeframe.SEM_SINAIS:
        return "sem sinais"
    if linha.status is StatusTimeframe.SEM_TRADES:
        return "sem trades"
    if recomendado is not None and linha is recomendado:
        return "RECOMENDADO"
    if linha.elegivel:
        return "aprovado"
    return f"reprovado: {linha.ressalvas[0]}" if linha.ressalvas else "reprovado"


# ---------------------------------------------------------------------------
# tabela
# ---------------------------------------------------------------------------


def tabela(comp: ComparacaoTimeframes, cores: bool = False) -> str:
    """As oito metricas lado a lado - a forma principal da comparacao."""
    recomendado = comp.melhor_equilibrio
    cabecalho = (
        f"  {'TF':<5s} {'trades':>7s} {'retorno':>10s} {'drawdown':>10s} {'PF':>7s} "
        f"{'sharpe':>7s} {'win':>7s} {'expect.':>11s} {'custos':>11s} {'nota':>6s}  situacao"
    )
    linhas = [_c(" TABELA COMPARATIVA", "negrito", ativo=cores), cabecalho, "  " + "─" * (LARGURA - 4)]

    for linha in comp.linhas:
        situacao = _situacao(linha, recomendado)
        corpo = (
            f"  {linha.timeframe:<5s} "
            f"{(str(linha.n_trades) if linha.resultado else '-'):>7s} "
            f"{_num(linha.retorno_pct, 2, '%', sinal=True):>10s} "
            f"{_num(linha.max_drawdown_pct, 2, '%'):>10s} "
            f"{_num(linha.profit_factor, 2):>7s} "
            f"{_num(linha.sharpe, 2):>7s} "
            f"{_num(None if linha.win_rate is None else linha.win_rate * 100, 1, '%'):>7s} "
            f"{(formata_dinheiro(linha.expectancy) if linha.expectancy is not None else '-'):>11s} "
            f"{(formata_dinheiro(linha.custos) if linha.custos is not None else '-'):>11s} "
            f"{(_num(linha.score, 1) if linha.status.rodou else '-'):>6s}  "
        )
        if situacao == "RECOMENDADO":
            linhas.append(_c(corpo + situacao, "verde", "negrito", ativo=cores))
        elif situacao.startswith("reprovado"):
            linhas.append(corpo + _c(situacao, "vermelho", ativo=cores))
        elif situacao == "aprovado":
            linhas.append(corpo + _c(situacao, "cinza", ativo=cores))
        else:
            linhas.append(corpo + _c(situacao, "cinza", ativo=cores))
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# graficos de barras
# ---------------------------------------------------------------------------


def barras(
    titulo: str,
    itens: Sequence[tuple[str, Optional[float]]],
    formato: Callable[[Optional[float]], str] = lambda v: _num(v, 2),
    destaque: Optional[str] = None,
    largura: int = 34,
    cores: bool = False,
    inverter_cor: bool = False,
) -> str:
    """Barras horizontais com zero no meio quando ha valores negativos.

    O valor vai escrito na ponta da barra: em terminal nao existe tooltip, e
    um eixo em ASCII nao carrega precisao.
    """
    valores = [v for _, v in itens if v is not None]
    if not valores:
        return f" {titulo}\n   (sem dados)"

    tem_negativo = any(v < 0 for v in valores)
    maximo = max(abs(v) for v in valores) or 1.0
    meia = largura // 2 if tem_negativo else largura

    linhas = [_c(f" {titulo}", "negrito", ativo=cores)]
    for rotulo, valor in itens:
        if valor is None:
            linhas.append(f"   {rotulo:<5s} │{' ' * largura}  -")
            continue
        blocos = int(round(abs(valor) / maximo * meia))
        if tem_negativo:
            if valor >= 0:
                corpo = " " * meia + "█" * blocos + " " * (meia - blocos)
            else:
                corpo = " " * (meia - blocos) + "█" * blocos + " " * meia
        else:
            corpo = "█" * blocos + " " * (largura - blocos)
        positivo = valor >= 0
        cor = ("vermelho" if positivo else "verde") if inverter_cor else ("verde" if positivo else "vermelho")
        marca = " ◀" if destaque and rotulo == destaque else ""
        linhas.append(f"   {rotulo:<5s} │{_c(corpo, cor, ativo=cores)}  {formato(valor)}{marca}")
    if tem_negativo:
        linhas.append(f"   {'':<5s} │{' ' * meia}└ zero")
    return "\n".join(linhas)


def graficos(comp: ComparacaoTimeframes, cores: bool = False) -> str:
    """Retorno, drawdown e nota final, um grafico por grandeza."""
    rodadas = comp.rodadas
    if not rodadas:
        return ""
    melhor = comp.melhor_equilibrio
    destaque = melhor.timeframe if melhor else None

    partes = [
        barras("RETORNO (%)", [(l.timeframe, l.retorno_pct) for l in rodadas],
               lambda v: _num(v, 2, "%", sinal=True), destaque, cores=cores),
        "",
        barras("MAX DRAWDOWN (%)", [(l.timeframe, l.max_drawdown_pct) for l in rodadas],
               lambda v: _num(v, 2, "%"), destaque, cores=cores, inverter_cor=True),
        "",
        barras("NOTA DE EQUILIBRIO (0-100)", [(l.timeframe, l.score) for l in rodadas],
               lambda v: _num(v, 1), destaque, cores=cores),
    ]
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# dispersao risco x retorno
# ---------------------------------------------------------------------------


def dispersao(comp: ComparacaoTimeframes, altura: int = 11, largura: int = 46, cores: bool = False) -> str:
    """Drawdown no eixo X, retorno no eixo Y - o grafico que mostra o trade-off.

    Cada eixo carrega uma grandeza so. O canto superior esquerdo (muito
    retorno, pouco drawdown) e' onde um timeframe bom mora.
    """
    pontos = [
        (l.timeframe, l.max_drawdown_pct, l.retorno_pct)
        for l in comp.rodadas
        if l.max_drawdown_pct is not None and l.retorno_pct is not None
    ]
    if len(pontos) < 2:
        return ""

    xs = [p[1] for p in pontos]
    ys = [p[2] for p in pontos]
    x0, x1 = 0.0, max(max(xs), 0.01) * 1.15
    y0, y1 = min(min(ys), 0.0), max(max(ys), 0.01)
    if y1 <= y0:
        y1 = y0 + 0.01

    grade = [[" "] * largura for _ in range(altura)]

    linha_zero = int(round((y1 - 0.0) / (y1 - y0) * (altura - 1)))
    if 0 <= linha_zero < altura:
        for col in range(largura):
            grade[linha_zero][col] = "·"  # linha do zero, discreta

    for rotulo, x, y in pontos:
        col = int(round((x - x0) / (x1 - x0) * (largura - 1)))
        lin = int(round((y1 - y) / (y1 - y0) * (altura - 1)))
        col = max(0, min(largura - 1, col))
        lin = max(0, min(altura - 1, lin))
        grade[lin][col] = "●"
        etiqueta = rotulo
        inicio = col + 2 if col + 2 + len(etiqueta) < largura else col - len(etiqueta) - 1
        if inicio >= 0:
            for k, ch in enumerate(etiqueta):
                if inicio + k < largura and grade[lin][inicio + k] in (" ", "·"):
                    grade[lin][inicio + k] = ch

    linhas = [
        _c(" RISCO x RETORNO", "negrito", ativo=cores),
        "   (canto superior esquerdo = mais retorno com menos drawdown)",
    ]
    for i, fila in enumerate(grade):
        valor = y1 - (y1 - y0) * i / (altura - 1)
        linhas.append(f"   {_num(valor, 2, '%', sinal=True):>9s} ┤{''.join(fila)}")
    linhas.append("   " + " " * 9 + " └" + "─" * largura)
    linhas.append(f"   {'':>9s}  {_num(x0, 2, '%'):<6s}{'drawdown maximo →'.center(largura - 14)}{_num(x1, 2, '%'):>6s}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# notas do vencedor
# ---------------------------------------------------------------------------


def painel_notas(linha: LinhaComparacao, cores: bool = False) -> str:
    """Como a nota do timeframe recomendado foi formada."""
    if not linha.notas:
        return ""
    linhas = [_c(f" COMO {linha.timeframe} CHEGOU A NOTA {linha.score:.1f}", "negrito", ativo=cores)]
    for n in linha.notas:
        blocos = int(round(n.nota * 10))
        barra = "█" * blocos + "·" * (10 - blocos)
        linhas.append(
            f"   {n.nome:<22s} [{barra}] {n.nota * 100:>5.1f}  peso {n.peso:.2f}"
            f"   {n.detalhe}"
        )
    linhas.append(
        f"   {'nota bruta':<22s} {linha.score_bruto:>17.1f}"
    )
    linhas.append(
        f"   {'confianca da amostra':<22s} {'x' + f'{linha.confianca:.2f}':>17s}"
        f"   {linha.n_trades} trade(s): a amostra sustenta essa fracao da nota"
    )
    linhas.append(f"   {'nota final':<22s} {linha.score:>17.1f}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina_comparacao(comp: ComparacaoTimeframes, cores: bool = False) -> str:
    """A tela Comparar Timeframes inteira."""
    periodo = "-"
    if comp.inicio and comp.fim:
        periodo = f"{comp.inicio:%d/%m/%Y} a {comp.fim:%d/%m/%Y}"

    linhas = [
        _c(f"COMPARAR TIMEFRAMES · {comp.symbol} · {comp.estrategia} · {periodo}", "negrito", ativo=cores),
        "─" * LARGURA,
        f" capital {formata_dinheiro(comp.capital_inicial)} · mesma estrategia, mesmos dados, "
        f"mesmos custos - so o timeframe muda",
        "",
        tabela(comp, cores),
        "",
    ]

    graf = graficos(comp, cores)
    if graf:
        linhas.append(graf)
        linhas.append("")
    disp = dispersao(comp, cores=cores)
    if disp:
        linhas.append(disp)
        linhas.append("")

    melhor = comp.melhor_equilibrio
    linhas.append(_c(" VEREDITO", "negrito", ativo=cores))
    cor_veredito = "verde" if melhor else "amarelo"
    linhas.append("   " + _c(comp.veredito, cor_veredito, ativo=cores))
    linhas.append(
        "   a nota combina retorno ajustado ao risco, consistencia e peso dos custos, e "
        "depois e' descontada"
    )
    linhas.append(
        "   pela confianca da amostra - maior retorno, sozinho, nao elege timeframe nenhum."
    )

    if melhor:
        linhas.append("")
        linhas.append(painel_notas(melhor, cores))

    reprovados = [l for l in comp.rodadas if not l.elegivel]
    if reprovados:
        linhas.append("")
        linhas.append(_c(" POR QUE OS OUTROS NAO PASSARAM", "negrito", ativo=cores))
        for l in reprovados:
            motivo = "; ".join(l.ressalvas) or l.motivo or "sem ressalva registrada"
            linhas.append(f"   {l.timeframe:<5s} {motivo}")

    if comp.avisos:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for aviso in dict.fromkeys(comp.avisos):
            linhas.append(f"   · {aviso}")
    return "\n".join(linhas)
