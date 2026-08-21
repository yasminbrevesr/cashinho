# Arquitetura do Cashinho

## Fluxo conceitual

```text
Market Data → Data Quality → Market Context → Technical Analysis
→ Multi-Timeframe Engine → Strategy Engine → Opportunity → Scoring
→ Contrarian Auditor → Risk Manager → Position Sizing
→ Genial Ticket Generator → Paper Broker / Confirmação Humana → Journal
```

Estratégias **não** enviam ordens. Elas produzem `Opportunity`. Somente o pipeline
chama o Risk Manager, e nenhuma rejeição de risco pode ser sobrescrita.

## Camadas

| Camada | Diretório | Pode importar |
|---|---|---|
| Domínio | `src/cashinho/domain` | nada do projeto, exceto `domain` |
| Portas | `src/cashinho/ports` | `domain` |
| Núcleo | `src/cashinho/core` | `domain`, `ports` |
| Adaptadores | `src/cashinho/adapters` | `domain`, `ports`, `core`, `config` |
| Interface | `app/` | apenas `cashinho.*` |

A interface nunca contém regra de negócio. O domínio nunca importa `streamlit`,
`sqlalchemy` ou qualquer provedor externo.

## Decisões vigentes

| # | Decisão | ADR |
|---|---|---|
| D1 | `src`-layout e Streamlit como camada fina | ADR-0001 |
| D2 | Portas e adaptadores | ADR-0001 |
| D3 | `Clock` como porta; `datetime.now()` proibido no domínio | ADR-0002 |
| D4 | Invariante de candle fechado imposto pelo tipo | ADR-0003 |
| D5 | UTC interno, fuso local só na apresentação | ADR-0002 |
| D6 | `Decimal` no domínio financeiro, `float` no pipeline numérico | ADR-0004 |
| D7 | Modelos de domínio separados dos de persistência | ADR-0005 |
| D8 | Risk Manager fora do caminho da estratégia | — |
| D9 | Capacidade do provedor limita o modo de operação | — |
| D10 | Score derivado de vetor de fatores explícito | — |

## Fases

| Fase | Escopo | Estado |
|---|---|---|
| 0 | Bootstrap: packaging, lint, testes, CI, segredos | concluída |
| 1 | Domínio, enums, Clock, calendário B3 | concluída |
| 2 | Portas, provider de fixture, `CandleStore`, portão de qualidade | próxima |
| Marco A | Fatia vertical: análise de um ativo visível na interface | — |
| 3 | Indicadores puros e motor multi-timeframe | — |
| 4 | Risk Manager, position sizing, kill switch | — |
| 5 | Ciclo de vida da oportunidade, scoring, auditor contrário | — |
| 6 | Persistência com Alembic e diário completo | — |
| 7 | Genial Ticket Generator e System Health completo | — |

Estratégias, scanner, backtest, replay e paper broker só depois da Fase 7.
