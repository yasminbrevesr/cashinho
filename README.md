# Cashinho

Plataforma de análise quantitativa, backtesting, paper trading e apoio operacional
para ativos da B3.

> **Estado atual: fundação (v0.1.0).**
> Não há estratégias, scanner, provedor de dados nem integração com corretora.
> **Nenhuma ordem real é enviada por esta aplicação.**

## Princípio

O Cashinho não procura operações a qualquer custo. Os estados válidos de uma
oportunidade são:

`SETUP APROVADO` · `AGUARDANDO GATILHO` · `SETUP REJEITADO` · `NÃO OPERAR` · `EXPIRADO`

`NÃO OPERAR` é uma decisão perfeitamente válida.

## Requisitos

- Python 3.11 ou superior

## Instalação

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -e .
pip install pytest pytest-cov ruff mypy
```

## Configuração

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

O `.env` **nunca** é versionado. Apenas o `.env.example` vai para o repositório.
Nenhuma credencial de corretora é usada nesta fase.

## Dados de desenvolvimento

```bash
python scripts/generate_fixtures.py
```

Gera séries **sintéticas e determinísticas** em `data/fixtures/` (três ativos,
cinco timeframes). Não são preços reais da B3: servem para exercitar o pipeline
sem depender de rede. Backtest sobre esses arquivos mede o código, nunca a
estratégia.

Os arquivos não são versionados — a geração é reprodutível a partir da semente e
da data-âncora fixas no script.

## Execução

```bash
streamlit run app/main.py
```

A aplicação abre no modo definido em `CASHINHO_MODE`. O padrão é `PAPER`, e o modo
fica visível de forma permanente na barra lateral de todas as páginas.

## Testes

```bash
pytest                       # suíte completa
pytest -m "not integration"  # apenas testes unitários
pytest --cov=cashinho        # com cobertura
ruff check . && mypy         # lint e tipos
```

## Modos de operação

| Modo | Estado |
|---|---|
| `RESEARCH` | habilitado |
| `BACKTEST` | habilitado |
| `REPLAY` | habilitado |
| `PAPER` | habilitado (padrão) |
| `ASSISTED` | **bloqueado em runtime** |
| `LIVE` | **bloqueado em runtime** |

`ASSISTED` e `LIVE` são recusados por `Settings.ensure_mode_allowed()` enquanto o
provedor em tempo real, o Risk Manager completo e o gerador de boleta validado não
existirem. A falha acontece no arranque, não no envio de uma ordem.

## Estrutura

```text
src/cashinho/
├── config/       configuração central e hash de reprodutibilidade
├── domain/       modelos puros (Pydantic), sem I/O
├── ports/        Protocols: Clock, MarketDataProvider
├── core/         regras e cálculo (time, data_quality)
├── adapters/     persistência, provedores, geração de boleta
└── observability/ logging estruturado

app/              interface Streamlit (camada fina, sem regra de negócio)
tests/            unit, integration e golden
```

## Regras de desenvolvimento

1. **Tempo.** É proibido chamar `datetime.now()` dentro de `src/cashinho/`.
   Toda leitura de tempo passa pela porta `Clock`.
2. **Fuso.** Interno sempre UTC e *aware*. Datetime naive é rejeitado na validação.
   A conversão para horário local só acontece na apresentação.
3. **Candle fechado.** Indicadores e motores de decisão recebem séries via
   `closed_only()` ou `require_closed()`. Nunca a série crua.
4. **Precisão.** `Decimal` para preço, quantidade e resultado. `float` apenas
   dentro do pipeline numérico, com conversão explícita em `CandleSeries.to_frame()`.
5. **Dados.** Nenhuma cotação é inventada e preço antigo nunca é apresentado como
   atual. Sem dados válidos, o resultado é `ANÁLISE BLOQUEADA`.
6. **Risco.** O Risk Manager tem autoridade superior à estratégia. Estratégias não
   enviam ordens: produzem oportunidades.
7. **Segredos.** Nenhuma credencial no repositório. Somente variáveis de ambiente.

## Limitações declaradas nesta versão

- O único provedor é `CsvHistoricalProvider`, que lê arquivos locais. Não há
  cotação ao vivo: `get_quote()` falha por princípio, em vez de devolver o último
  fechamento como se fosse preço atual.
- As séries de desenvolvimento são sintéticas. Nenhum dado real da B3 está integrado.
- A tela de Análise executa inspeção histórica (`RESEARCH`) mesmo com o sistema em
  `PAPER`, porque a fonte atual não fornece tempo real. O rebaixamento é declarado
  na própria tela.
- O calendário de feriados da B3 não está carregado; dias úteis são aproximados.
- O schema do banco é criado com `create_all`. O Alembic assume as migrações na
  Fase 6, antes de o diário acumular dados que não possam ser perdidos.
- Os limites de risco vêm de valores padrão de configuração, não do estado
  operacional real.
