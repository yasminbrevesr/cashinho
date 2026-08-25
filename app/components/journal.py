"""Projeções visuais do diário auditável."""

from __future__ import annotations

from typing import Any

from cashinho.domain.journal import DecisionJournalRecord, PaperTradeJournalRecord


def decision_rows(records: list[DecisionJournalRecord]) -> list[dict[str, Any]]:
    return [
        {
            "Ativo": record.symbol,
            "Decisão": "ENTRADA LIBERADA" if record.should_enter else "NÃO ENTRAR",
            "Lado": record.side if record.should_enter else "—",
            "Timeframe": record.timeframe or "—",
            "Confiança": record.confidence,
            "Horário (UTC)": record.timestamp,
            "Motivo principal": record.primary_reason,
        }
        for record in records
    ]


def paper_trade_rows(records: list[PaperTradeJournalRecord]) -> list[dict[str, Any]]:
    return [
        {
            "ID": record.paper_order_id[:8],
            "Ativo": record.symbol,
            "Lado": record.side,
            "Entrada": record.fill_price or record.entry,
            "Saída": record.close_price,
            "Resultado": record.pnl_value,
            "Resultado em R": record.result_in_r,
            "Status": record.status,
            "Motivo": record.close_reason,
        }
        for record in records
    ]
