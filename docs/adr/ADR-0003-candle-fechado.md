# ADR-0003 — Invariante de candle fechado no tipo

**Data:** 2026-08-20 · **Estado:** aceita

## Contexto
Estratégias que exigem fechamento não podem receber o candle em formação. Tratar
isso como convenção transfere o risco para a disciplina de quem escreve o código.

## Decisão
`Candle.is_closed` e dois caminhos explícitos em `CandleSeries`:
`closed_only()` descarta o candle em formação; `require_closed()` levanta
`UnclosedCandleError`. A validação garante que apenas o último candle da série
pode estar aberto.

## Consequências
- Uso indevido vira erro em tempo de execução, não resultado silenciosamente errado.
- `require_closed()` é preferível quando descartar o último candle mascararia um
  erro de orquestração do pipeline.
