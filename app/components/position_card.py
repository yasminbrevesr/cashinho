"""Card principal para uma posição PAPER aberta."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from cashinho.pipeline.paper_broker import PaperOrder
from cashinho.pipeline.paper_performance import unrealized_pnl
from cashinho.pipeline.position_manager import PositionAction, PositionDecision


def _money(value: Decimal | None) -> str:
    return "—" if value is None else f"R$ {value:,.2f}"


def render_position_card(position: PaperOrder, decision: PositionDecision) -> None:
    """Mostra somente a decisão de gestão; a entrada não compete visualmente."""

    result = unrealized_pnl(position, decision.current_price)
    side_label = "COMPRA" if position.ticket.side == "BUY" else "VENDA"
    with st.container(border=True):
        title, side = st.columns([2, 1])
        title.markdown(f"## POSIÇÃO PAPER ABERTA · {position.ticket.symbol}")
        side.markdown(f"### {side_label}")

        first = st.columns(4)
        first[0].metric("Entrada", _money(position.fill_price))
        first[1].metric("Preço atual", _money(decision.current_price))
        first[2].metric("Stop", _money(position.ticket.stop))
        first[3].metric("Alvo", _money(position.ticket.target))
        second = st.columns(2)
        second[0].metric("Resultado", _money(result.pnl_value if result else None))
        second[1].metric(
            "Resultado em R", "—" if result is None else f"{result.result_in_r:+.2f}R"
        )

        if decision.action is PositionAction.HOLD:
            st.success("🟢 MANTER POSIÇÃO")
        else:
            st.error("🔴 SAIR DA POSIÇÃO")
        st.markdown(f"**Motivo:** {decision.primary_reason}")
        if decision.action is PositionAction.EXIT and not decision.can_execute:
            st.warning(
                "SAÍDA RECOMENDADA, ainda não executada: não há bid/ask ativo e válido."
            )
