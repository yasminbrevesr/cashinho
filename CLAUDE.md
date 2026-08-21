# Cashinho

Plataforma de análise quantitativa e apoio operacional para ativos da B3.
Python 3.11+, Streamlit, Pydantic v2, pandas, Plotly, SQLAlchemy, SQLite.

**Nenhuma ordem real é enviada por esta aplicação.**

## Comandos

```bash
pip install -e .                      # instala o pacote em modo editável
python scripts/generate_fixtures.py   # gera séries sintéticas em data/fixtures
streamlit run app/main.py             # sobe a interface
pytest                                # suíte completa
pytest -m "not integration"           # apenas testes unitários
ruff check .                          # lint
mypy                                  # tipos (strict)
```

Rodar `pytest`, `ruff check .` e `mypy` antes de qualquer commit. Os três
precisam passar.

## Regras invioláveis

1. **Nunca chame `datetime.now()` dentro de `src/cashinho/`.** Use a porta
   `Clock` (`SystemClock`, `FrozenClock`, `ReplayClock`). Há teste de
   arquitetura que falha se isso for violado.
2. **Todo datetime é aware e em UTC.** Naive é rejeitado na validação. A
   conversão para `America/Sao_Paulo` só acontece na apresentação e no
   calendário da B3.
3. **Indicadores e motores de decisão recebem apenas séries fechadas.** Use
   `CandleSeries.closed_only()` ou `require_closed()`, nunca a série crua.
4. **`Decimal` para preço, quantidade, risco e resultado.** `float` apenas
   dentro do pipeline numérico. A única ponte é `CandleSeries.to_frame()`.
5. **Nunca invente cotação e nunca apresente preço antigo como atual.** Sem
   dados válidos, o resultado é `ANÁLISE BLOQUEADA`.
6. **O Risk Manager tem autoridade superior à estratégia.** Estratégias não
   enviam ordens: produzem `Opportunity`. Nenhuma rejeição de risco pode ser
   sobrescrita.
7. **Nenhum segredo no repositório.** Só variáveis de ambiente e `.env.example`
   sem valores preenchidos.
8. **A UI é camada fina.** `app/` não contém regra de negócio e o domínio não
   importa `streamlit`, `sqlalchemy` nem `plotly`. Há testes de arquitetura
   fazendo cumprir isso.
9. **Não faça commit, push, merge ou PR sem autorização explícita.**

## Estados válidos de uma oportunidade

`SETUP APROVADO` · `AGUARDANDO GATILHO` · `SETUP REJEITADO` · `NÃO OPERAR` ·
`EXPIRADO`

`NÃO OPERAR` é uma decisão perfeitamente válida. O sistema não procura
operações a qualquer custo.

## Modos

`RESEARCH`, `BACKTEST`, `REPLAY` e `PAPER` estão habilitados. `ASSISTED` e
`LIVE` são recusados no arranque por `Settings.ensure_mode_allowed()`. O padrão
é `PAPER`.

`ProviderCapabilities` limita o modo: fonte sem tempo real não habilita
`PAPER`, `ASSISTED` nem `LIVE`.

## Estrutura

```text
src/cashinho/
├── config/        configuração central e hash de reprodutibilidade
├── domain/        modelos Pydantic puros, sem I/O
├── ports/         Protocols: Clock, MarketDataProvider
├── core/          time, data_quality, indicators
├── adapters/      persistence (SQLAlchemy), providers (CSV)
├── pipeline/      orquestração: market_data, indicators
└── observability/ logging estruturado

app/               Streamlit: main.py, pages/, components/
tests/             unit/, integration/, golden/
docs/adr/          decisões arquiteturais registradas
```

Camadas e o que cada uma pode importar estão em `docs/ARCHITECTURE.md`.
Decisões e seus motivos estão em `docs/adr/`.

## Estado atual

Concluído e testado:

- Fundação: domínio, `Clock`, calendário B3, persistência, configuração,
  logging, nove páginas navegáveis com indicador permanente de modo.
- Camada de dados: `MarketDataProvider`, `CsvHistoricalProvider`, portão de
  qualidade com dez verificações, pipeline de carga.
- Indicadores: SMA, EMA, VWAP, RSI, MACD, ATR, Bollinger, com painel
  configurável na tela de Análise.

330 testes, `mypy` strict limpo, ~98% de cobertura.

Próximo passo previsto: motor multi-timeframe (`60m` contexto → `15m`
tendência → `5m` setup → `1m` gatilho), sem look-ahead na fronteira entre
timeframes.

## Limitações declaradas

- **Não há fonte de dados real.** O único provider lê CSV local. As séries de
  `data/fixtures/` são **sintéticas** — backtest sobre elas mede o código,
  nunca a estratégia.
- O calendário de feriados da B3 não está carregado; dias úteis são aproximados.
- O schema do banco usa `create_all`. O Alembic assume as migrações antes de o
  diário acumular dados que não possam ser perdidos.
- A tela de Análise executa inspeção histórica (`RESEARCH`) mesmo com o sistema
  em `PAPER`, porque a fonte atual não fornece tempo real. O rebaixamento é
  declarado na própria tela, nunca silencioso.

## Convenções

- Testes em português, nomes descrevendo o comportamento esperado.
- Docstrings explicam **por que**, não o que o código faz.
- Valores esperados nos testes vêm de cálculo independente, nunca copiados da
  saída da implementação.
- Qualquer bug capaz de alterar dinheiro, posição, risco ou resultado gera
  teste de regressão.
- Indicadores não emitem sinal de compra ou venda. Há teste parametrizado que
  falha se alguma coluna virar veredito.
