# ADR-0004 — `Decimal` no domínio financeiro

**Data:** 2026-08-20 · **Estado:** aceita

## Contexto
Dimensionamento de posição e apuração de resultado acumulam drift quando feitos em
ponto flutuante. Indicadores, por outro lado, precisam de numpy.

## Decisão
Preço, quantidade, risco monetário e resultado usam `Decimal` quantizado em duas
casas. `float` aparece apenas dentro do pipeline numérico. A única ponte
autorizada é `CandleSeries.to_frame()`. No SQLite, `Decimal` é persistido como
texto (`DecimalText`), porque `Numeric` seria armazenado como float.

## Consequências
- Testes de regressão financeira ficam estáveis.
- Custo: conversões explícitas nas fronteiras.
