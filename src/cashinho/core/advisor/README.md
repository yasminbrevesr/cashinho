# Timeframe Advisor (`cashinho.core.advisor`)

Em qual granularidade operar este ativo **agora**.

```
python -m cashinho.core.advisor --ativo PETR4 --dias 10
python -m cashinho.core.advisor --card          # só o card do dashboard
python -m cashinho.core.advisor --atual 5m      # liga a histerese
```

```python
from cashinho.core.advisor import TimeframeAdvisor

rec = TimeframeAdvisor().avaliar(serie_de_1m)
rec.setup_timeframe              # "5m"
rec.market_fit_score             # 86.0
rec.statistical_evidence_score   # None quando não há histórico
```

## A pergunta certa

Não é *"qual timeframe ganhou mais hoje"* — essa pergunta transforma uma manhã
sortuda em conclusão. É: **o comportamento atual do ativo favorece qual
granularidade, e há evidência para afirmar isso?**

Por isso a saída tem **dois números que nunca se misturam**:

| | o que é | quando falta |
|---|---|---|
| `market_fit_score` | o comportamento de agora favorece este timeframe | sempre calculável |
| `statistical_evidence_score` | há histórico que sustente | **`None`** — nunca inventado |

```
2m    Market Fit 94   ·   Statistical Evidence 35   ·   Confidence 58
      "o comportamento atual favorece 2m, mas ainda não há evidência"
```

## O score: seis componentes, pesos configuráveis

| componente | peso | o que mede |
|---|---|---|
| Regime | 25% | o timeframe está alinhado com o contexto? |
| Estrutura | 20% | **densidade** de pivôs e taxa de falso rompimento |
| Ruído | 15% | razão de eficiência: quanto do caminho virou deslocamento |
| Liquidez | 15% | volume e, quando há book, quanto o spread come da amplitude |
| Performance | 15% | expectância/PF do histórico — **indisponível sem histórico** |
| Estabilidade | 10% | a eficiência se manteve entre as últimas janelas? |

Cada nota vem com a frase que a explica. Componente sem dado fica
**indisponível** e sai da média — nunca vira zero, que seria uma afirmação.

Duas escolhas que vale registrar:

- **Estrutura mede densidade, não contagem.** Contar pivôs premiava o
  timeframe mais ruidoso: o 1m tem muito mais pivôs que o 15m, e isso não o
  torna melhor de operar.
- **Ciclo não é ruído.** Uma oscilação periódica de 19 minutos é operável no
  1m e imprestável no 15m. A razão de eficiência captura isso corretamente, e
  há teste fixando a distinção.

## Confiança

Cai por três motivos, e cada um aparece na saída: poucos candles, pouco (ou
nenhum) histórico, e componentes indisponíveis. Mais a vantagem sobre o
segundo colocado — liderança apertada é liderança frágil.

**Uma operação de +4R não vence trinta de +0,45R.** A nota de performance é
multiplicada pelo peso da amostra (`√(trades/30)`, saturando em 1), então
sorte recente entra descontada. Abaixo de 30 candles a confiança é
`INSUFICIENTE` e não vira recomendação, por melhor que esteja o score.

## Histerese

Trocar 5m → 2m → 5m → 3m é pior que ficar num timeframe mediano: nenhum setup
matura. Duas travas configuráveis:

```
5m em 82  vs  2m em 84   →  MANTER (margem mínima de 8 pontos)
5m em 63  vs  2m em 88   →  TROCAR
```

Mais um **tempo mínimo de permanência** (15 min). A carência é ignorada quando
o timeframe atual desabou — esperar quinze minutos num timeframe ruim não
ajuda ninguém.

## Sem look-ahead

A recomendação em `T` usa **só** o que existia até `T`. Isso não é disciplina
de quem chama: vem da `MTFVista`, que só entrega barra já fechada e que já
tinha os testes anti-look-ahead do módulo multi-timeframe.

O teste decisivo: avaliar em `T`, depois **trocar todo o futuro** por outra
série e avaliar de novo — o ranking tem que sair idêntico.

## Resampling

Reusa o `MTFEngine`, que já existia: reamostra 1m → 2m/3m/5m/10m/15m/30m/60m
sob demanda, respeitando a sessão da B3. `open` primeiro, `high` máximo, `low`
mínimo, `close` último, `volume` somado — verificado candle a candio contra os
1m que o compõem.

**Independente de provider.** Entra uma `Series` de 1m, venha do MetaTrader,
CSV, replay ou backtest. Este módulo não importa `MetaTrader5` — há teste.

## Contexto, setup e gatilho são perguntas diferentes

```
Contexto  15m     onde se lê a direção maior
Setup      5m     onde a operação é desenhada
Gatilho    3m     onde a entrada é confirmada
```

O gatilho é sempre **estritamente mais fino** que o setup. Quando o setup já é
o timeframe mais fino disponível, o gatilho vem `None` com o aviso — repetir o
setup ali sugeriria uma camada de confirmação que não existe.

## Status

| status | significado |
|---|---|
| `RECOMMENDED` | há um timeframe claramente melhor agora |
| `KEEP_CURRENT` | o atual segue adequado; trocar seria ruído |
| `LOW_CONFIDENCE` | há um líder, mas sem sustentação — **sem recomendação confiável** |
| `INSUFFICIENT_DATA` | dados insuficientes para avaliar |

Não há vencedor forçado: dois dos quatro status dizem explicitamente que não
dá para recomendar.

## Horário do dia

Toda recomendação sai carimbada com o período (`ABERTURA`, `MEIO`, `TARDE`,
`FECHAMENTO`). Ainda **não** há estatística por período — os cortes são
declarados, não descobertos. O que a estrutura impede é o sistema virar "o
melhor timeframe do dia", que é a pergunta errada: a recomendação é
**ativo + regime + horário + setup**.

## Limitações

- **Performance é sempre indisponível hoje**: nada alimenta `Estatistica`
  ainda. O gancho existe (`avaliar(..., estatisticas={"5m": ...})`) e o
  backtest por timeframe é quem vai preenchê-lo.
- **Spread só existe com book** — MT5. Nas demais fontes, Liquidez usa só
  volume e a confiança cai.
- A faixa de densidade de pivô é primeira calibração, feita contra dados
  sintéticos. Precisa de revisão com dado real.
