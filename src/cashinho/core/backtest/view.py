"""Pagina Backtest: curva de capital, drawdown, lista de trades e metricas."""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .models import BacktestResult, MotivoSaida, PontoEquity
from ..ui import c as _c

LARGURA = 74

def _num(valor: Optional[float], casas: int = 2, sufixo: str = "") -> str:
    if valor is None:
        return "-"
    return f"{valor:,.{casas}f}{sufixo}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor: Optional[float], casas: int = 2) -> str:
    return "-" if valor is None else _num(valor, casas, "%")


# ---------------------------------------------------------------------------
# curva de capital e drawdown
# ---------------------------------------------------------------------------


def curva_de_capital(
    resultado: BacktestResult, altura: int = 12, largura: int = 64, cores: bool = False
) -> str:
    """Curva de patrimonio em ASCII, com a linha do capital inicial marcada."""
    pontos = _reamostra([p.equity for p in resultado.equity], largura)
    if len(pontos) < 2:
        return "(dados insuficientes para desenhar a curva)"

    base = resultado.capital_inicial
    pmin, pmax = min(min(pontos), base), max(max(pontos), base)
    if pmax <= pmin:
        pmax = pmin + max(abs(pmin) * 0.001, 0.01)

    def linha_de(valor: float) -> int:
        return int(round((pmax - valor) / (pmax - pmin) * (altura - 1)))

    grade = [[" "] * len(pontos) for _ in range(altura)]
    linha_base = linha_de(base)
    for col in range(len(pontos)):
        grade[linha_base][col] = "─"
    for col, valor in enumerate(pontos):
        grade[linha_de(valor)][col] = "•"

    linhas = [_c(" CURVA DE CAPITAL", "negrito", ativo=cores)]
    for i, fila in enumerate(grade):
        valor = pmax - (pmax - pmin) * i / (altura - 1)
        marca = "  <- capital inicial" if i == linha_base else ""
        linhas.append(f"  {formata_dinheiro(valor):>14s} ┤{''.join(fila)}{marca}")
    linhas.append("  " + " " * 14 + " └" + "─" * len(pontos))
    return "\n".join(linhas)


def curva_de_drawdown(
    resultado: BacktestResult, altura: int = 6, largura: int = 64, cores: bool = False
) -> str:
    """Drawdown em % ao longo do tempo (quanto mais fundo, pior)."""
    serie = _reamostra(resultado.drawdown_series(), largura)
    if len(serie) < 2:
        return ""
    pior = max(serie) or 1.0
    grade = [[" "] * len(serie) for _ in range(altura)]
    for col, valor in enumerate(serie):
        nivel = int(round(valor / pior * (altura - 1)))
        for i in range(nivel + 1):
            grade[i][col] = "█"

    linhas = [_c(" DRAWDOWN", "negrito", ativo=cores)]
    for i, fila in enumerate(grade):
        valor = pior * i / (altura - 1) if altura > 1 else 0.0
        rotulo = _pct(-valor) if valor else _pct(0.0)  # evita "-0,00%"
        linhas.append(f"  {rotulo:>14s} ┤{_c(''.join(fila), 'vermelho', ativo=cores)}")
    return "\n".join(linhas)


def _reamostra(valores: Sequence[float], largura: int) -> list[float]:
    """Comprime a serie para caber na largura, mantendo o formato da curva."""
    n = len(valores)
    if n <= largura:
        return list(valores)
    passo = n / largura
    return [valores[min(int(i * passo), n - 1)] for i in range(largura)]


# ---------------------------------------------------------------------------
# metricas e trades
# ---------------------------------------------------------------------------


def painel_metricas(resultado: BacktestResult, cores: bool = False) -> str:
    m = resultado.metricas
    cor_retorno = "verde" if m.retorno_total > 0 else ("vermelho" if m.retorno_total < 0 else "cinza")
    linhas = [_c(" METRICAS", "negrito", ativo=cores)]

    def par(rotulo_a, valor_a, rotulo_b, valor_b) -> str:
        return f"   {rotulo_a:<18s}{valor_a:>14s}    {rotulo_b:<18s}{valor_b:>14s}"

    linhas.append(par("retorno total", _c(formata_dinheiro(m.retorno_total), cor_retorno, ativo=cores),
                      "retorno %", _pct(m.retorno_total_pct)))
    linhas.append(par("trades", str(m.n_trades), "exposicao (tempo)", _pct(m.exposicao_tempo_pct)))
    linhas.append(par("win rate", _pct(m.win_rate * 100), "loss rate", _pct(m.loss_rate * 100)))
    linhas.append(par("payoff", _num(m.payoff, 2), "profit factor", _num(m.profit_factor, 2)))
    linhas.append(par("expectancy", formata_dinheiro(m.expectancy), "expectancy (R)", _num(m.expectancy_em_r, 3)))
    linhas.append(par("max drawdown", formata_dinheiro(m.max_drawdown), "max drawdown %", _pct(m.max_drawdown_pct)))
    linhas.append(par("sharpe", _num(m.sharpe, 2), "sortino", _num(m.sortino, 2)))
    linhas.append(par("ganho medio", formata_dinheiro(m.ganho_medio), "perda media", formata_dinheiro(m.perda_media)))
    linhas.append(par("melhor trade", formata_dinheiro(m.melhor_trade), "pior trade", formata_dinheiro(m.pior_trade)))
    linhas.append(par("custos totais", formata_dinheiro(m.custos_totais), "dias", str(m.dias)))
    return "\n".join(linhas)


def lista_de_trades(resultado: BacktestResult, limite: int = 20, cores: bool = False) -> str:
    linhas = [_c(f" TRADES ({len(resultado.trades)})", "negrito", ativo=cores)]
    if not resultado.trades:
        linhas.append("   nenhum trade no periodo")
        return "\n".join(linhas)

    linhas.append(
        "   " + f"{'#':>3s} {'entrada':<12s} {'saida':<12s} {'dir':<7s} {'qtd':>6s} "
        f"{'preco':>9s} {'saida':>9s} {'motivo':<10s} {'resultado':>12s} {'R':>6s}"
    )
    for i, t in enumerate(resultado.trades[:limite], start=1):
        cor = "verde" if t.venceu else ("vermelho" if t.perdeu else "cinza")
        linhas.append(
            "   "
            + f"{i:>3d} {t.entrada_em:%d/%m %H:%M} {t.saida_em:%d/%m %H:%M} "
            + f"{t.direcao.value:<7s} {t.quantidade:>6d} {t.entrada_preco:>9.2f} {t.saida_preco:>9.2f} "
            + f"{t.motivo.value:<10s} "
            + _c(f"{formata_dinheiro(t.resultado):>12s}", cor, ativo=cores)
            + f" {t.resultado_em_r:>6.2f}"
        )
    if len(resultado.trades) > limite:
        linhas.append(f"   ... e mais {len(resultado.trades) - limite} trade(s)")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina(resultado: BacktestResult, cores: bool = False, limite_trades: int = 20) -> str:
    """A pagina Backtest inteira."""
    periodo = "-"
    if resultado.inicio and resultado.fim:
        periodo = f"{resultado.inicio:%d/%m/%Y} a {resultado.fim:%d/%m/%Y}"

    linhas = [
        _c(f"BACKTEST · {resultado.symbol} · {resultado.timeframe} · {periodo}", "negrito", ativo=cores),
        "─" * LARGURA,
    ]
    if resultado.experimental:
        linhas.append(
            _c("⚠  ESTRATEGIA DE VALIDACAO - RESULTADO NAO PROVA NADA SOBRE O FUTURO",
               "amarelo", "negrito", ativo=cores)
        )
    linhas.append(
        f" estrategia {resultado.estrategia} · capital {formata_dinheiro(resultado.capital_inicial)}"
        f" -> {formata_dinheiro(resultado.capital_final)}"
    )
    linhas.append("")
    linhas.append(curva_de_capital(resultado, cores=cores))
    dd = curva_de_drawdown(resultado, cores=cores)
    if dd:
        linhas.append("")
        linhas.append(dd)
    linhas.append("")
    linhas.append(painel_metricas(resultado, cores))
    linhas.append("")
    linhas.append(lista_de_trades(resultado, limite_trades, cores))

    if resultado.rejeicoes_do_risco:
        linhas.append("")
        linhas.append(_c(" SINAIS BARRADOS", "negrito", ativo=cores))
        linhas.append(
            f"   {resultado.sinais_acionaveis} sinal(is) acionavel(is) de "
            f"{resultado.sinais_avaliados} avaliado(s)"
        )
        for codigo, quantas in sorted(resultado.rejeicoes_do_risco.items(), key=lambda x: -x[1]):
            linhas.append(f"   · {codigo}: {quantas}x")

    if resultado.avisos:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for aviso in dict.fromkeys(resultado.avisos):
            linhas.append(f"   · {aviso}")
    return "\n".join(linhas)


def resumo(resultado: BacktestResult) -> str:
    """Uma linha, para comparar rodadas."""
    m = resultado.metricas
    return (
        f"{resultado.symbol} {resultado.timeframe} | {resultado.estrategia} | "
        f"retorno {_pct(m.retorno_total_pct)} | {m.n_trades} trades | "
        f"win {_pct(m.win_rate * 100, 1)} | PF {_num(m.profit_factor, 2)} | "
        f"DD {_pct(m.max_drawdown_pct)}"
    )
