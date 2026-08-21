"""Visualizacao da estrutura no terminal.

Tres saidas, da mais curta para a mais detalhada:

- :func:`resumo` - uma linha, para varredura de varios ativos;
- :func:`painel` - pivos, suporte/resistencia, Fibonacci e eventos em texto;
- :func:`grafico` - grafico ASCII com os pivos marcados, as zonas de suporte
  e resistencia desenhadas e as zonas de Fibonacci sombreadas.

Tudo devolve ``str``: quem chama decide se imprime, manda para um arquivo ou
serve numa interface web (o payload estruturado esta em
:meth:`MarketStructure.para_dict`).
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Series, formata_dinheiro
from .models import Level, MarketStructure, Regime, TipoEvento, TipoPivo

# marcadores
TOPO = "▲"      # triangulo para cima
FUNDO = "▼"     # triangulo para baixo
PRECO = "·"     # ponto do fechamento
SOMBRA_FIB = "░"  # bloco leve das zonas de Fibonacci
LINHA_FORTE = "═"
LINHA_FRACA = "─"
LINHA_FIB = "┈"
CONFLUENCIA = "◆"

_CORES = {
    "alta": "\033[32m",
    "baixa": "\033[31m",
    "neutro": "\033[33m",
    "fraco": "\033[90m",
    "reset": "\033[0m",
    "negrito": "\033[1m",
}


def _c(texto: str, cor: str, ativo: bool) -> str:
    if not ativo or cor not in _CORES:
        return texto
    return f"{_CORES[cor]}{texto}{_CORES['reset']}"


def _cor_do_regime(regime: Regime) -> str:
    return {Regime.ALTA: "alta", Regime.BAIXA: "baixa", Regime.LATERAL: "neutro"}[regime]


def _hora(ts) -> str:
    return ts.strftime("%H:%M")


# ---------------------------------------------------------------------------
# resumo de uma linha
# ---------------------------------------------------------------------------


def resumo(e: MarketStructure, cores: bool = False) -> str:
    """Uma linha por ativo - para comparar varios de uma vez."""
    partes = [
        f"{e.symbol} {e.timeframe}",
        _c(f"{e.tendencia.regime.value} ({e.tendencia.sequencia}, {e.tendencia.forca:.2f})",
           _cor_do_regime(e.tendencia.regime), cores),
        formata_dinheiro(e.preco),
    ]
    if e.suporte:
        partes.append(f"sup {formata_dinheiro(e.suporte.mid)}")
    if e.resistencia:
        partes.append(f"res {formata_dinheiro(e.resistencia.mid)}")
    if e.fib:
        zona = e.fib.zona_do_preco(e.preco)
        partes.append(f"fib {zona.nome}" if zona else "fib fora das zonas")
    else:
        partes.append("sem fib")
    if e.eventos:
        ultimo = e.eventos[-1]
        partes.append(ultimo.tipo.value)
    return " | ".join(partes)


# ---------------------------------------------------------------------------
# painel de texto
# ---------------------------------------------------------------------------


def painel(e: MarketStructure, cores: bool = False, max_pivos: int = 6) -> str:
    """Leitura completa da estrutura em texto."""
    linhas: list[str] = []
    cabecalho = f"{e.symbol} · {e.timeframe} · {_hora(e.ts)} · {formata_dinheiro(e.preco)}"
    linhas.append(_c(cabecalho, "negrito", cores))
    linhas.append("─" * max(len(cabecalho), 60))

    linhas.append(
        f"TENDENCIA   {_c(e.tendencia.descricao, _cor_do_regime(e.tendencia.regime), cores)}"
    )
    linhas.append(f"            forca {e.tendencia.forca:.2f} · ATR {formata_dinheiro(e.atr)}")

    linhas.extend(_secao_pivos(e, cores, max_pivos))
    linhas.extend(_secao_niveis(e, cores))
    linhas.extend(_secao_fibonacci(e, cores))
    linhas.extend(_secao_eventos(e, cores))
    return "\n".join(linhas)


def _secao_pivos(e: MarketStructure, cores: bool, max_pivos: int) -> list[str]:
    linhas = ["", _c("PIVOS", "negrito", cores)]
    if not e.pivos:
        linhas.append("  nenhum pivo confirmado ainda")
        return linhas

    topo = f"topo {formata_dinheiro(e.topo.preco)} ({_hora(e.topo.ts)})" if e.topo else "topo -"
    fundo = f"fundo {formata_dinheiro(e.fundo.preco)} ({_hora(e.fundo.ts)})" if e.fundo else "fundo -"
    linhas.append(
        f"  atuais: {_c(topo, 'baixa', cores)} · {_c(fundo, 'alta', cores)}"
        f"  ({len(e.pivos)} pivos, {len(e.swing_highs) + len(e.swing_lows)} significativos)"
    )
    significativos = {p.indice for p in e.swing_highs + e.swing_lows}
    for p in e.pivos[-max_pivos:]:
        marca = TOPO if p.tipo is TipoPivo.TOPO else FUNDO
        etiqueta = "swing" if p.indice in significativos else "ruido"
        linhas.append(
            f"    {marca} {p.tipo.value:5s} {formata_dinheiro(p.preco):>12s}  {_hora(p.ts)}"
            f"  confirmado {_hora(p.ts_confirmacao)}  [{etiqueta}]"
        )
    return linhas


def _secao_niveis(e: MarketStructure, cores: bool) -> list[str]:
    linhas = ["", _c("SUPORTE / RESISTENCIA", "negrito", cores)]
    if e.zona_atual:
        linhas.append(f"  preco DENTRO da zona {_faixa(e.zona_atual)}")
    for nivel in reversed(e.resistencias):
        linhas.append(f"  R  {_descreve_nivel(nivel, e.preco, cores)}")
    if not e.resistencias:
        linhas.append("  R  nenhuma resistencia mapeada acima")
    for nivel in e.suportes:
        linhas.append(f"  S  {_descreve_nivel(nivel, e.preco, cores)}")
    if not e.suportes:
        linhas.append("  S  nenhum suporte mapeado abaixo")
    return linhas


def _faixa(nivel: Level) -> str:
    return f"{formata_dinheiro(nivel.low)} - {formata_dinheiro(nivel.high)}"


def _descreve_nivel(nivel: Level, preco: float, cores: bool) -> str:
    cor = "baixa" if nivel.tipo == "resistencia" else "alta"
    distancia = nivel.distancia_pct(preco)
    barra = _barra(nivel.forca)
    return (
        f"{_c(_faixa(nivel), cor, cores)}  {nivel.toques}x  forca {barra} {nivel.forca:.2f}"
        f"  ({distancia:+.2f}%)"
    )


def _barra(valor: float, largura: int = 5) -> str:
    cheias = int(round(valor * largura))
    return "█" * cheias + "·" * (largura - cheias)


def _secao_fibonacci(e: MarketStructure, cores: bool) -> list[str]:
    linhas = ["", _c("FIBONACCI", "negrito", cores)]
    if e.fib is None:
        linhas.append(f"  nao desenhado: {e.motivo_sem_fib}")
        return linhas

    s = e.fib.swing
    sentido = "alta" if s.eh_alta else "baixa"
    linhas.append(
        f"  perna de {sentido}: {formata_dinheiro(s.inicio.preco)} ({_hora(s.inicio.ts)})"
        f" -> {formata_dinheiro(s.fim.preco)} ({_hora(s.fim.ts)})"
        f"  ·  {s.amplitude_atr:.1f} ATR / {s.amplitude_pct:.2f}%"
    )
    for nivel in e.fib.retracoes:
        linhas.append(_linha_fib(nivel, e.preco, cores))
    for nivel in e.fib.extensoes:
        linhas.append(_linha_fib(nivel, e.preco, cores))

    if e.fib.zonas:
        linhas.append("  zonas:")
        for z in e.fib.zonas:
            aqui = " <= preco aqui" if z.contem(e.preco) else ""
            linhas.append(
                f"    {z.nome:9s} {formata_dinheiro(z.low)} - {formata_dinheiro(z.high)}"
                f"  {z.descricao}{_c(aqui, 'neutro', cores)}"
            )
    return linhas


def _linha_fib(nivel, preco: float, cores: bool) -> str:
    marca = f" {CONFLUENCIA} confluencia com {nivel.confluencia.tipo}" if nivel.tem_confluencia else ""
    aqui = " <= preco aqui" if abs(nivel.preco - preco) < 1e-9 else ""
    return (
        f"    {nivel.rotulo:>7s}  {formata_dinheiro(nivel.preco):>12s}"
        f"  [{nivel.tipo}]{_c(marca, 'neutro', cores)}{aqui}"
    )


def _secao_eventos(e: MarketStructure, cores: bool) -> list[str]:
    linhas = ["", _c("EVENTOS", "negrito", cores)]
    if not e.eventos:
        linhas.append("  nenhum evento relevante na janela")
        return linhas
    for ev in e.eventos:
        cor = {"COMPRA": "alta", "VENDA": "baixa"}.get(ev.direcao.value, "neutro")
        linhas.append(
            f"  {_hora(ev.ts)}  {_c(ev.tipo.value.upper(), cor, cores)}"
            f" ({ev.direcao.value.lower()}, forca {ev.forca:.2f}): {ev.descricao}"
        )
    return linhas


# ---------------------------------------------------------------------------
# grafico ASCII
# ---------------------------------------------------------------------------


def grafico(
    serie: Series,
    e: MarketStructure,
    altura: int = 18,
    largura: int = 70,
    mostrar_pivos: bool = True,
    mostrar_niveis: bool = True,
    mostrar_fib: bool = True,
    cores: bool = False,
) -> str:
    """Grafico de texto com pivos, zonas de S/R e zonas de Fibonacci.

    Cada coluna e' um candle (os ultimos ``largura``). As tres camadas podem
    ser ligadas e desligadas para nao poluir a leitura.
    """
    candles = serie.candles[-largura:]
    if not candles or altura < 4:
        return "(sem dados suficientes para o grafico)"

    base = len(serie) - len(candles)
    pmin = min(c.low for c in candles)
    pmax = max(c.high for c in candles)
    if pmax <= pmin:
        pmax = pmin + max(pmin * 0.001, 0.01)
    folga = (pmax - pmin) * 0.06
    pmin, pmax = pmin - folga, pmax + folga

    def linha_de(preco: float) -> Optional[int]:
        if not (pmin <= preco <= pmax):
            return None
        return int(round((pmax - preco) / (pmax - pmin) * (altura - 1)))

    grade = [[" "] * len(candles) for _ in range(altura)]
    rotulos: dict[int, list[str]] = {}

    def anota(r: Optional[int], texto: str) -> None:
        if r is None:
            return
        rotulos.setdefault(r, [])
        if texto not in rotulos[r]:
            rotulos[r].append(texto)

    # 1) zonas de Fibonacci ao fundo
    if mostrar_fib and e.fib:
        for zona in e.fib.zonas:
            topo_r = linha_de(zona.high)
            base_r = linha_de(zona.low)
            if topo_r is None and base_r is None:
                continue
            r1 = topo_r if topo_r is not None else 0
            r2 = base_r if base_r is not None else altura - 1
            for r in range(min(r1, r2), max(r1, r2) + 1):
                for col in range(len(candles)):
                    if grade[r][col] == " ":
                        grade[r][col] = SOMBRA_FIB
            anota(min(r1, r2), f"fib {zona.nome}")

    # 2) niveis de Fibonacci
    if mostrar_fib and e.fib:
        for nivel in e.fib.retracoes + e.fib.extensoes:
            r = linha_de(nivel.preco)
            if r is None:
                continue
            for col in range(len(candles)):
                if grade[r][col] in (" ", SOMBRA_FIB):
                    grade[r][col] = LINHA_FIB
            marca = f" {CONFLUENCIA}" if nivel.tem_confluencia else ""
            anota(r, f"{nivel.rotulo} {formata_dinheiro(nivel.preco)}{marca}")

    # 3) suportes e resistencias
    if mostrar_niveis:
        zonas = list(e.suportes) + list(e.resistencias) + ([e.zona_atual] if e.zona_atual else [])
        for nivel in zonas:
            r = linha_de(nivel.mid)
            if r is None:
                continue
            traco = LINHA_FORTE if nivel.forca >= 0.6 else LINHA_FRACA
            for col in range(len(candles)):
                if grade[r][col] in (" ", SOMBRA_FIB, LINHA_FIB):
                    grade[r][col] = traco
            sigla = "R" if nivel.tipo == "resistencia" else "S"
            anota(r, f"{sigla} {formata_dinheiro(nivel.mid)} ({nivel.toques}x)")

    # 4) caminho do preco
    for col, c in enumerate(candles):
        r = linha_de(c.close)
        if r is not None:
            grade[r][col] = PRECO

    # 5) pivos por cima de tudo
    if mostrar_pivos:
        for p in e.pivos:
            col = p.indice - base
            if not (0 <= col < len(candles)):
                continue
            r = linha_de(p.preco)
            if r is None:
                continue
            grade[r][col] = TOPO if p.tipo is TipoPivo.TOPO else FUNDO

    # montagem
    linhas: list[str] = []
    titulo = f"{e.symbol} · {e.timeframe} · {formata_dinheiro(e.preco)} · {e.tendencia.regime.value}"
    linhas.append(_c(titulo, "negrito", cores))
    for r in range(altura):
        preco_da_linha = pmax - (pmax - pmin) * r / (altura - 1)
        eixo = f"{formata_dinheiro(preco_da_linha):>12s}"
        corpo = "".join(grade[r])
        sufixo = ("  " + " · ".join(rotulos[r])) if r in rotulos else ""
        linhas.append(f"{eixo} ┤{corpo}{sufixo}")
    inicio = _hora(candles[0].ts)
    fim = _hora(candles[-1].ts)
    linhas.append(" " * 12 + "└" + "─" * len(candles))
    linhas.append(" " * 13 + f"{inicio}{' ' * max(len(candles) - len(inicio) - len(fim), 1)}{fim}")
    linhas.append(_legenda(mostrar_pivos, mostrar_niveis, mostrar_fib))
    return "\n".join(linhas)


def _legenda(mostrar_pivos: bool, mostrar_niveis: bool, mostrar_fib: bool) -> str:
    """So descreve os marcadores das camadas que estao ligadas."""
    itens = [f"{PRECO} fechamento"]
    if mostrar_pivos:
        itens += [f"{TOPO} topo", f"{FUNDO} fundo"]
    if mostrar_niveis:
        itens += [f"{LINHA_FORTE} zona forte", f"{LINHA_FRACA} zona fraca"]
    if mostrar_fib:
        itens += [f"{LINHA_FIB} nivel fib", f"{SOMBRA_FIB} zona fib"]
    return "  " + "  ".join(itens)
