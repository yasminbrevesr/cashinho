# Cashinho

Copiloto de análise para day trade na B3. **Ele analisa e orienta — não envia
ordens.** Toda a execução hoje é simulada (Paper Broker), e a ponte com a
corretora é uma tela de digitação: a boleta da Genial preenchida para você
copiar.

---

## Como ver funcionando (2 minutos)

Precisa de **Python 3.9+** e nada mais — o núcleo é stdlib puro.

```bash
git clone <url-do-repo> cashinho
cd cashinho
git checkout claude/day-trade-bot-b3-a91olv

export PYTHONPATH=src            # Windows: set PYTHONPATH=src
python -m cashinho.core.scanner --semente 3 --atr-min 0.05
```

Isso roda a **varredura completa** — dados → multi-timeframe → estratégia →
oportunidade → score → auditor → risco — sobre pregões sintéticos
reproduzíveis, e mostra o ranking:

```
 SCANNER · 10 ativo(s) · ordenado por score
  ATIVO    SCORE  SETUP                 DIR     STATUS             TF     R:R      RISCO
  VALE3     67.1  5m: pullback          VENDA   SETUP REJEITADO    5m    0.36   R$ 0,12/ac
  B3SA3     53.0  5m: failed_breakout   VENDA   AGUARDANDO GATILHO 5m    0.48   R$ 0,13/ac
  PETR4      0.0  -                     -       SEM SETUP          -     0.00            -
```

> **Sem `--semente 3 --atr-min 0.05` a varredura padrão não acha nada** — os
> pregões sintéticos padrão têm volatilidade abaixo do filtro. Varrer sem achar
> é o resultado esperado na maior parte do tempo real, mas para *ver o sistema
> trabalhar* use os parâmetros acima.

Para entender **por que** um ativo parou onde parou:

```bash
python -m cashinho.core.scanner --semente 3 --atr-min 0.05 --detalhe B3SA3
```

```
 FLUXO
   ✔  4. Strategy: WAIT: AGUARDANDO GATILHO: 5m: failed_breakout
   ✔  5. Opportunity: setup pronto no 5m para 'reversao de falso rompimento',
                      aguardando gatilho no 1m
   ✖  6. Score: score 53, mas o setup ainda nao esta pronto
   ·  7. Auditor: nao executada
```

Nenhum número aparece sem a conta que o gerou.

### Ver um trade inteiro nascer e morrer

```bash
python -m cashinho.core.replay --velocidade maxima
```

O replay reproduz um pregão candle a candle, com o pipeline rodando **como se
fosse ao vivo** — nenhum componente enxerga candle futuro:

```
 EVENTOS (5)
   13:05 s sinal    BUY: SETUP APROVADO: reversao de falso rompimento
   13:05 E entrada  COMPRA 683 @ 29.30 (score 64)
   13:05 S stop     stop em 29.12
   13:05 A alvo     alvo em 29.51
   14:55 X saida    saida por stop_loss @ 29.10

  PETR4 · 475/475 candles · 1 sinal · 1 entrada · P&L -142.56
```

Sim, esse trade deu prejuízo. É o tipo de resultado que o sistema mostra sem
maquiar.

---

## As onze telas

Todas aceitam `--help`, quase todas aceitam `--json` e `--sem-cor`.

| comando | o que mostra |
|---|---|
| `python -m cashinho.core.scanner` | **comece por aqui** — varredura da watchlist, ranking, `--detalhe ATIVO`, `--boleta ATIVO` |
| `python -m cashinho.core.saude` | System Health: 7 componentes, ONLINE/DEGRADED/OFFLINE, e se dá para operar agora |
| `python -m cashinho.core.backtest` | curva de capital, drawdown, lista de trades, 11 métricas |
| `python -m cashinho.core.replay` | reproduz um pregão candle a candle, com o pipeline rodando como se fosse ao vivo |
| `python -m cashinho.core.contexto` | Ibovespa, dólar, juros, petróleo, índices — e o quanto disso ele sabe |
| `python -m cashinho.core.noticias` | agenda de eventos de risco; `--modelo` gera o calendário para preencher |
| `python -m cashinho.core.broker` | Paper Trading: saldo, posições, ordens, P&L, kill switch |
| `python -m cashinho.core.risk` | Risk Manager: limites e TRADING LIBERADO / BLOQUEADO |
| `python -m cashinho.core.diario` | diário de trades e estatística por setup, ativo, horário |
| `python -m cashinho.core.validacao` | TRAIN/VALIDATION/TEST e walk-forward |
| `python -m cashinho.core.log` | log estruturado do pregão |
| `python -m cashinho.data` | market data: origem, status, idade e qualidade do dado |

Exemplos que valem a pena:

```bash
python -m cashinho.core.saude                                   # dá para operar agora?
python -m cashinho.core.backtest --ativo PETR4 --dias 10        # backtest completo
python -m cashinho.core.replay --velocidade maxima              # um pregão inteiro
python -m cashinho.core.validacao --walk-forward                # a estratégia se sustenta?
python -m cashinho.core.scanner --semente 3 --atr-min 0.05 --boleta B3SA3
```

---

## Dados: histórico e tempo real são coisas diferentes

Uma pergunta separa as duas metades da camada de dados:

> **Este dado serve para decidir uma entrada agora, ou para estudar o passado?**

| | Historical Market Data | Realtime Market Data |
|---|---|---|
| serve para | backtest, pesquisa, validação, dashboard histórico | scanner intradiário, paper ao vivo, análise assistida |
| tolera atraso | sim | **não** |
| provedores hoje | `demo`, `csv`, `brapi`, `yahoo` | nenhum implementado |

Um provedor **gratuito ou atrasado é ótimo para desenvolvimento e backtesting
e imprestável para sinal de day trade**. O Cashinho sabe a diferença e recusa
o segundo uso em vez de improvisar — não existe fallback silencioso de
"realtime caiu, usa o atrasado".

```bash
cp .env.example .env        # e preencha
python -m cashinho.data --providers
python -m cashinho.data --ativo PETR4 --provider demo --timeframe 1d
```

A fonte padrão é `demo` — **pregões sintéticos, não são preços reais**.

Para **brapi.dev**: crie um token em brapi.dev, preencha `BRAPI_TOKEN` no
`.env` e declare os três campos do seu plano (`BRAPI_ATRASO_SEGUNDOS`,
`BRAPI_TIMEFRAMES`, `BRAPI_REQUISICOES_POR_MINUTO`) lendo a documentação. O
Cashinho **não adivinha característica de plano**: sem esses valores ele
assume o pior caso e não libera análise de tempo real.

Para **Yahoo**: `pip install yfinance` e `--fonte yahoo`. Tem ~15 min de
atraso, declarado nas capacidades — serve para pesquisa, não para entrada.

Também dá para usar CSV: `--fonte csv --pasta dados` com arquivos
`PETR4-5m.csv` (`timestamp,open,high,low,close,volume`).

Detalhes, estados do dado (`ONLINE`/`DELAYED`/`STALE`/`DEGRADED`/`OFFLINE`) e
como adicionar um provedor novo: `src/cashinho/data/README.md`.

---

## Testes

```bash
pip install pytest
python -m pytest -q          # 1583 testes, ~80s
```

---

## Como o sistema pensa

```
Market Data → Contexto → Multi-Timeframe → Estratégia → Oportunidade
           → Score → Auditor → Risk Manager → Paper Broker → Diário
```

Cada etapa pode barrar; nenhuma pode pular a seguinte. Quatro regras que
valem em todo o código:

1. **Nada de look-ahead.** Uma barra de 60m só existe depois de fechada.
   Backtest, replay e vista multi-timeframe são testados de forma adversarial.
2. **Nenhum número sem a conta.** O score aparece com as onze notas, pesos e
   contribuições; um desconto por notícia é uma linha, não um número que mudou
   sozinho.
3. **Ausência não é zero.** Sem fonte confiável, o campo fica vazio e marcado
   (`FONTE A CONFIRMAR`, `NOTÍCIAS INDISPONÍVEIS`) — nunca estimado.
4. **O que é crítico vira bloqueio, não aviso.** Kill switch, `NÃO OPERAR`,
   Market Data offline barrando ordem nova.

Cada módulo tem seu próprio README em `src/cashinho/core/<modulo>/README.md`,
e `REVISAO.md` traz a revisão técnica completa do MVP com o que ficou
pendente.

---

## O que ele **não** faz

- não envia ordem para corretora nenhuma (a boleta é para você digitar);
- não inventa cotação nem notícia;
- não promete que a estratégia funciona — a estratégia atual existe para
  validar a arquitetura, e o módulo de validação serve para mostrar quando ela
  **não** funciona fora do período em que foi ajustada.
