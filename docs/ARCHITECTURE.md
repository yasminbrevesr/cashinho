# Arquitetura do Cashinho

## Fluxo conceitual

```text
Market Data → Data Quality → Market Regime → Technical Analysis
→ Multi-Timeframe → Timeframe Advisor → Entry Signal → FinalDecision
→ Risk Manager → Paper Broker → Position Manager → P&L → Journal
```

Estratégias **não** enviam ordens. Elas produzem `Opportunity`. Somente o pipeline
chama o Risk Manager, e nenhuma rejeição de risco pode ser sobrescrita.

Antes do fill, `FinalDecision` é a única autoridade para `ENTRADA LIBERADA` ou
`NÃO ENTRAR`. Depois do fill, `PositionManager` assume exclusivamente a decisão
`HOLD/EXIT`; ele nunca cria uma posição contrária. STOP e TARGET continuam sob
autoridade do `PaperBroker`. Saídas dinâmicas voltam ao broker por
`close_position()` e ficam bloqueadas sem bid/ask válido.

O backtest reutiliza as duas decisões em ordem cronológica e compara duas bases:
STOP+TARGET e STOP+TARGET+PositionManager. O cálculo de P&L é compartilhado com
o PAPER, em `paper_performance.py`.

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
| D11 | Entrada (`FinalDecision`) e gestão (`PositionDecision`) são separadas | — |
| D12 | Paper Broker é a única autoridade de execução simulada | — |
| D13 | Saída dinâmica sem book produz recomendação, nunca fill inventado | — |

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

O produto atual permanece estritamente PAPER. `NÃO ENTRAR` e `MANTER` são
decisões válidas; não existe caminho de execução real.
