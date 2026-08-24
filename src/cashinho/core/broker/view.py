"""Pagina Paper Trading: saldo, patrimonio, posicoes, ordens, operacoes e P&L."""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import formata_dinheiro
from .base import Broker, broker_base
from .modelos import Balance, Operacao, Order, OrderStatus, Position
from ..ui import c as _c

LARGURA = 84

_COR_DO_STATUS = {
    OrderStatus.PENDENTE: "amarelo",
    OrderStatus.EXECUTADA: "verde",
    OrderStatus.CANCELADA: "cinza",
    OrderStatus.REJEITADA: "vermelho",
}


def _sinal(valor: float) -> str:
    return _c_valor(valor)


def _c_valor(valor: float, cores: bool = False) -> str:
    texto = f"{valor:+,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    cor = "verde" if valor > 0 else ("vermelho" if valor < 0 else "cinza")
    return _c(f"R$ {texto}", cor, ativo=cores)


# ---------------------------------------------------------------------------
# kill switch
# ---------------------------------------------------------------------------


def faixa_kill_switch(motivo: str = "", cores: bool = False) -> str:
    """O aviso de que a simulacao esta travada."""
    rotulo = "KILL SWITCH ACIONADO - NOVAS OPERACOES BLOQUEADAS".center(LARGURA - 2)
    linhas = [
        "╔" + "═" * (LARGURA - 2) + "╗",
        "║" + rotulo + "║",
        "╚" + "═" * (LARGURA - 2) + "╝",
    ]
    texto = "\n".join(_c(l, "vermelho", "negrito", ativo=cores) for l in linhas)
    if motivo:
        texto += "\n " + _c(motivo, "vermelho", ativo=cores)
    texto += "\n " + _c(
        "ordens de protecao (stop loss e take profit) continuam valendo - "
        "a trava impede abrir, nao sair", "cinza", ativo=cores
    )
    return texto


# ---------------------------------------------------------------------------
# blocos
# ---------------------------------------------------------------------------


def painel_saldo(saldo: Balance, pnl_aberto: float = 0.0, cores: bool = False) -> str:
    linhas = [_c(" CONTA", "negrito", ativo=cores)]
    linhas.append(
        f"   saldo em caixa   {formata_dinheiro(saldo.saldo):>16s}"
        f"      patrimonio  {formata_dinheiro(saldo.patrimonio):>16s}"
    )
    linhas.append(
        f"   exposicao        {formata_dinheiro(saldo.exposicao):>16s}"
        f"      retorno     {saldo.retorno_pct:>15.2f}%"
    )
    linhas.append(
        f"   P&L do dia       {_c_valor(saldo.pnl_dia, cores):>16s}"
        f"      P&L acumulado {_c_valor(saldo.pnl_acumulado, cores):>14s}"
    )
    if pnl_aberto:
        linhas.append(f"   P&L em aberto    {_c_valor(pnl_aberto, cores):>16s}"
                      f"      custos      {formata_dinheiro(saldo.custos_totais):>16s}")
    else:
        linhas.append(f"   custos totais    {formata_dinheiro(saldo.custos_totais):>16s}")
    return "\n".join(linhas)


def tabela_posicoes(posicoes: Sequence[Position], precos: Optional[dict] = None,
                    cores: bool = False) -> str:
    linhas = [_c(f" POSICOES ({len(posicoes)})", "negrito", ativo=cores)]
    if not posicoes:
        linhas.append("   nenhuma posicao aberta")
        return "\n".join(linhas)

    linhas.append(f"   {'ATIVO':<8s} {'DIR':<7s} {'QTD':>7s} {'PRECO MEDIO':>13s} "
                  f"{'ATUAL':>10s} {'EXPOSICAO':>14s} {'P&L ABERTO':>14s}")
    for p in posicoes:
        preco = (precos or {}).get(p.symbol.upper(), p.preco_medio)
        pnl = p.pnl_aberto(preco)
        linhas.append(
            f"   {p.symbol:<8s} {p.direcao.value:<7s} {p.quantidade:>7d} "
            f"{formata_dinheiro(p.preco_medio):>13s} {preco:>10.2f} "
            f"{formata_dinheiro(p.exposicao):>14s} {_c_valor(pnl, cores):>14s}"
        )
    return "\n".join(linhas)


def tabela_ordens(ordens: Sequence[Order], titulo: str = "ORDENS ABERTAS",
                  cores: bool = False, limite: Optional[int] = None) -> str:
    mostradas = list(ordens)[:limite] if limite else list(ordens)
    linhas = [_c(f" {titulo} ({len(ordens)})", "negrito", ativo=cores)]
    if not mostradas:
        linhas.append("   nenhuma ordem")
        return "\n".join(linhas)

    linhas.append(f"   {'ID':<15s} {'ATIVO':<8s} {'TIPO':<12s} {'LADO':<7s} {'QTD':>7s} "
                  f"{'PRECO':>10s} {'STATUS':<11s}")
    for o in mostradas:
        preco = o.preco_executado or o.preco_limite or o.preco_disparo
        linhas.append(
            f"   {o.id:<15s} {o.symbol:<8s} {o.tipo.value:<12s} {o.side.value:<7s} "
            f"{o.quantidade:>7d} {(f'{preco:.2f}' if preco else '-'):>10s} "
            + _c(f"{o.status.value:<11s}", _COR_DO_STATUS[o.status], ativo=cores)
        )
        if o.motivo and o.status in (OrderStatus.REJEITADA, OrderStatus.CANCELADA):
            linhas.append(f"   {'':<15s} └ {o.motivo}")
    if limite and len(ordens) > limite:
        linhas.append(f"   ... e mais {len(ordens) - limite}")
    return "\n".join(linhas)


def tabela_operacoes(operacoes: Sequence[Operacao], cores: bool = False,
                     limite: Optional[int] = 10) -> str:
    mostradas = list(operacoes)[-limite:] if limite else list(operacoes)
    linhas = [_c(f" OPERACOES ({len(operacoes)})", "negrito", ativo=cores)]
    if not mostradas:
        linhas.append("   nenhuma operacao encerrada")
        return "\n".join(linhas)

    linhas.append(f"   {'ATIVO':<8s} {'DIR':<7s} {'QTD':>7s} {'ENTRADA':>10s} {'SAIDA':>10s} "
                  f"{'MOTIVO':<12s} {'RESULTADO':>14s}")
    for o in mostradas:
        linhas.append(
            f"   {o.symbol:<8s} {o.direcao.value:<7s} {o.quantidade:>7d} "
            f"{o.preco_entrada:>10.2f} {o.preco_saida:>10.2f} {o.motivo:<12s} "
            f"{_c_valor(o.resultado, cores):>14s}"
        )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# pagina
# ---------------------------------------------------------------------------


def pagina(broker: Broker, cores: bool = False, limite_ordens: Optional[int] = None) -> str:
    """A pagina Paper Trading."""
    saldo = broker.get_balance()
    posicoes = broker.get_positions()
    abertas = broker.get_orders(abertas=True)
    todas = broker.get_orders()
    operacoes = broker.get_trades()

    precos = _precos_de(broker)
    pnl_aberto = sum(p.pnl_aberto(precos.get(p.symbol.upper(), p.preco_medio)) for p in posicoes)

    linhas = [
        _c(f"PAPER TRADING · {broker.nome} · simulacao", "negrito", ativo=cores),
        "─" * LARGURA,
    ]

    travado, motivo = _kill_switch(broker)
    if travado:
        linhas.append(faixa_kill_switch(motivo, cores))
        linhas.append("")

    linhas.append(painel_saldo(saldo, pnl_aberto, cores))
    linhas.append("")
    linhas.append(tabela_posicoes(posicoes, precos, cores))
    linhas.append("")
    linhas.append(tabela_ordens(abertas, "ORDENS ABERTAS", cores, limite_ordens))

    barradas = [o for o in todas if o.status is OrderStatus.REJEITADA]
    if barradas:
        linhas.append("")
        linhas.append(tabela_ordens(barradas, "ORDENS BARRADAS", cores, limite_ordens))

    linhas.append("")
    linhas.append(tabela_operacoes(operacoes, cores))

    avisos = getattr(broker, "avisos", [])
    if avisos:
        linhas.append("")
        linhas.append(_c(" AVISOS", "negrito", ativo=cores))
        for aviso in dict.fromkeys(avisos):
            linhas.append(f"   · {aviso}")
    return "\n".join(linhas)


def _precos_de(broker: Broker) -> dict:
    return getattr(broker_base(broker), "_precos", {}) or {}


def _kill_switch(broker: Broker) -> tuple[bool, str]:
    alvo = broker
    for _ in range(4):
        if alvo is None:
            break
        if getattr(alvo, "kill_switch_ativo", False):
            return True, getattr(alvo, "kill_switch_motivo", "")
        risco = getattr(alvo, "risco", None)
        if risco is not None and risco.estado.kill_switch is not None:
            return True, risco.estado.kill_switch.motivo
        alvo = getattr(alvo, "broker", None)
    return False, ""


def resumo(broker: Broker) -> str:
    """Uma linha."""
    s = broker.get_balance()
    return (
        f"patrimonio {formata_dinheiro(s.patrimonio)} | caixa {formata_dinheiro(s.saldo)} | "
        f"dia {s.pnl_dia:+.2f} | acumulado {s.pnl_acumulado:+.2f} | "
        f"{s.posicoes_abertas} posicao(oes), {s.ordens_abertas} ordem(ns)"
    )
