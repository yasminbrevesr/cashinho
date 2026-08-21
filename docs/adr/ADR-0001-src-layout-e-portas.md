# ADR-0001 — `src`-layout, portas e adaptadores

**Data:** 2026-08-20 · **Estado:** aceita

## Contexto
O Streamlit reexecuta o script inteiro a cada interação do usuário. Regra de
negócio dentro da interface se torna não determinística e não testável.

## Decisão
O pacote vive em `src/cashinho/` e a interface em `app/`, importando apenas
`cashinho.*`. Dependências externas são acessadas por `Protocol`s em `ports/`,
implementados em `adapters/`.

## Consequências
- Testes rodam contra o pacote, não contra o diretório de trabalho.
- Trocar de provedor de dados não toca em estratégia.
- Custo: uma camada de indireção a mais em cada integração externa.
