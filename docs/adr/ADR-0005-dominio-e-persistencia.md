# ADR-0005 — Modelos de domínio separados dos de persistência

**Data:** 2026-08-20 · **Estado:** aceita

## Contexto
O diário é o ativo de longo prazo do projeto: ele registra decisões reais e
alimenta a análise de desempenho por setup, ativo, horário e regime.

## Decisão
Modelos Pydantic em `domain/` e tabelas SQLAlchemy em `adapters/persistence/`,
com tradução concentrada em `mappers.py`.

## Consequências
- O domínio evolui sem forçar migração imediata do schema.
- Custo: mapeamento explícito e o risco de divergência entre as duas camadas,
  contido por testes de ida e volta.
