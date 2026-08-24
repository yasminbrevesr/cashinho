# Market Data (`cashinho.data`)

Uma pergunta separa esta camada em duas metades:

> **Este dado serve para decidir uma entrada agora, ou serve para estudar o
> passado?**

São coisas diferentes, e o Cashinho trata como diferentes.

```
                          CASHINHO
                              │
                    MarketDataService
              ┌───────────────┴───────────────┐
              ▼                               ▼
     HISTORICAL PROVIDER            REALTIME PROVIDER
              │                               │
          brapi / csv / demo            (metatrader - previsto)
              │                               │
   backtest, pesquisa, validacao      scanner intradiário,
                                      paper ao vivo
```

Estratégias, indicadores, scanner, backtest e Risk Manager **não sabem** qual
provedor está atrás. Todos falam com `MarketDataProvider`.

## Historical x Realtime

| | Historical | Realtime |
|---|---|---|
| serve para | backtest, pesquisa, dashboard histórico | scanner intradiário, paper ao vivo, análise assistida |
| tolera atraso | sim | **não** |
| provedor hoje | `demo`, `csv`, `brapi`, `yahoo` | nenhum implementado |

Um provedor gratuito e atrasado é **ótimo** para backtest e **imprestável**
para decidir entrada agora. Quem sabe a diferença é o `MarketDataService` — e
ele recusa a segunda em vez de improvisar.

### Sem fallback silencioso

```
provedor de tempo real caiu
        ↓
Cashinho NÃO troca por dado atrasado
        ↓
TempoRealIndisponivelError  +  REALTIME FEED OFFLINE na tela
```

Cair para o histórico e seguir tratando como mercado seria a falha mais cara
que esta camada pode ter. Por isso não existe esse caminho no código.

## Os cinco estados

| estado | significado |
|---|---|
| `ONLINE` | dado dentro da idade esperada **para aquele provedor** |
| `DELAYED` | o provedor **declara** atraso: nunca serve para entrada em tempo real |
| `STALE` | deveria estar atualizado e parou de atualizar |
| `DEGRADED` | provedor respondendo parcialmente |
| `OFFLINE` | não veio dado |

**Não há limite universal de "velho".** Um candle diário de sexta está em dia
na segunda; um candle de 1m de 40 minutos atrás está morto. O limite sai do
timeframe (`limite_de_stale`) e do atraso que o provedor declarou. Cotação tem
régua própria (`classificar_cotacao`): candle diário de ontem está em dia,
cotação de ontem não está.

## Capabilities: declarado, nunca deduzido

```python
Capacidades(candles_historicos=True, cotacao=True,
            cotacao_em_tempo_real=False, intradiario_1m=False,
            atraso_tipico_s=900)
```

A pergunta nunca é "será que dá certo?" — é "**está declarado** que dá?".
Capacidade não declarada é capacidade que não existe, e pedir a um provedor
algo que ele não declara levanta `CapacidadeAusenteError` em vez de adaptar
em silêncio.

`serve_para_day_trade` exige cotação em tempo real, 1m **e** atraso declarado
pequeno. **Atraso desconhecido não passa**: não saber o atraso é motivo para
não usar.

## brapi.dev — o que foi confirmado e o que não

A documentação da brapi **não pôde ser aberta** deste ambiente (o proxy de
rede bloqueia o domínio). O que está no código veio de páginas da própria
brapi obtidas por busca, e está separado assim:

**Confirmado** — base `https://brapi.dev/api`, autenticação
`Authorization: Bearer <token>`, endpoint `/quote/{tickers}` com `range` e
`interval`, alguns ativos respondendo sem token.

**Rota de cotação (v2), informada pelo dono do projeto:**

```
GET https://brapi.dev/api/v2/stocks/quote?symbols=B3SA3
        ↓
results[0].data      ← os campos da cotação vêm aninhados aqui
```

`BrapiMarketDataProvider.buscar_cotacao(symbol)` é a função tipada dessa rota:
devolve o dicionário de `results[0].data` já desembrulhado, com não-2xx
tratado (401/403 apontam o `BRAPI_TOKEN`, 429 aponta o freio, 5xx e timeout
são retentados, o resto não). `cotacao(symbol)` normaliza isso no modelo
`Cotacao` do projeto.

A rota antiga (`results[0]` sem `data`) continua sendo aceita: uma troca de
rota não pode virar campo faltando lá na frente.

**Não confirmado — por isso é configuração, não constante:**

| o quê | por quê | onde declarar |
|---|---|---|
| atraso do plano | fontes citam 15 **e** 30 min para o gratuito | `BRAPI_ATRASO_SEGUNDOS` |
| quais `interval` seu plano libera | não verificável | `BRAPI_TIMEFRAMES` |
| teto de requisições | varia por plano | `BRAPI_REQUISICOES_POR_MINUTO` |
| nomes dos campos da resposta | não verificável | `CAMPOS` em `brapi.py` |

Sem `BRAPI_ATRASO_SEGUNDOS`, o provedor assume que **não serve para tempo
real**. Sem `BRAPI_TIMEFRAMES`, ele recusa qualquer timeframe em vez de
chutar o que o plano libera. E se a resposta não trouxer nenhum dos apelidos
de `CAMPOS`, ele **levanta erro dizendo qual campo faltou** — nunca preenche
com zero.

## Qualidade dos dados

`ValidadorDeQualidade` confere o que só aparece no conjunto: timestamp
duplicado ou fora de ordem, candle no futuro, buraco dentro do pregão, série
velha demais, fuso ausente. **Dado inválido bloqueia a análise que depende
dele** — não existe "corrigir" série, só aceitar ou recusar com o motivo.

O `Candle` já recusa o impossível um a um (máxima abaixo da mínima, preço
zerado); o validador é a camada do conjunto.

## Fuso horário

Regra única: **todo timestamp interno é timezone-aware**. Timestamp ingênuo é
recusado no `Candle`, na `Cotacao` e no validador. Fontes que entregam epoch
ou ISO com `Z` são convertidas na borda para horário de Brasília; comparar UTC
com BRT dá o mesmo instante, e há teste para isso.

## Como usar

```python
from cashinho.data import Finalidade, montar_servico

servico = montar_servico()                      # lê o .env
leitura = servico.candles("PETR4", "1d", 30, Finalidade.BACKTEST)

leitura.fonte        # "brapi"
leitura.status       # StatusDados.DELAYED
leitura.qualidade    # OK / DADOS INVALIDOS
leitura.utilizavel   # serve para a finalidade pedida?
```

```
python -m cashinho.data --providers
python -m cashinho.data --ativo PETR4 --provider demo --timeframe 1d
python -m cashinho.data --ativo PETR4 --finalidade scanner_intradiario
```

## Adicionar um provedor novo

1. herde de `MarketDataProvider`;
2. **declare `capacidades`** — o que não for declarado não existe;
3. implemente `candles()`; implemente `cotacao()` só se declarar `cotacao=True`;
4. registre em `IMPLEMENTADOS` na `fabrica.py`;
5. escreva os testes com resposta simulada — nenhum teste desta camada toca a
   rede.

É assim que o `MetaTraderMarketDataProvider` entra depois: nada fora desta
pasta precisa mudar.
