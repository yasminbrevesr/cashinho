# ADR-0002 — `Clock` como porta e UTC interno

**Data:** 2026-08-20 · **Estado:** aceita

## Contexto
Market Replay, backtest e testes exigem controle do instante lógico do sistema.
Chamadas diretas a `datetime.now()` tornam esse controle impossível. Datetime
naive é a origem mais comum de erro silencioso em análise intradiária.

## Decisão
`datetime.now()` é proibido dentro de `src/cashinho/`. Toda leitura passa por
`Clock` (`SystemClock`, `FrozenClock`, `ReplayClock`). Todo datetime do domínio é
*aware* e normalizado para UTC por `ensure_utc`; naive é rejeitado na validação.
Conversão para `America/Sao_Paulo` só na apresentação e no calendário da B3.

## Consequências
- `CandleSeries.assert_no_lookahead(clock)` passa a ser possível.
- Nenhum teste depende do relógio da máquina.
- Custo: injetar o relógio em toda função sensível a tempo.
