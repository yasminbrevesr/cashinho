# Backtest Engine (`cashinho.core.backtest`)

Simula uma estrategia candle a candle, com custos, horario e Risk Manager. O
engine nao depende de interface nenhuma: recebe serie e estrategia, devolve
`BacktestResult`.

```python
from cashinho.core.backtest import BacktestConfig, BacktestEngine
from cashinho.core.strategy import BaselineTendenciaVolumeATR

config = BacktestConfig(symbol="PETR4", capital_inicial=100_000)
resultado = BacktestEngine(BaselineTendenciaVolumeATR(), config).rodar(serie_1m)
```

## A regra que sustenta o resultado

**Quem decide no fechamento do candle so executa no candle seguinte.** Isso
esta na propria ordem das etapas dentro de cada candle:

```
candle i chega
  0. saida decidida no fechamento de i-1 executa na ABERTURA de i
  1. entrada decidida no fechamento de i-1 executa na ABERTURA de i
  2. stop e alvo sao testados contra a maxima e a minima de i
  3. horario de encerramento zera a posicao
  -- candle i FECHA --
  4. so agora a estrategia olha os dados e pode gerar ordem para i+1
  5. o patrimonio e' marcado a mercado
```

Nenhuma etapa enxerga preco que ainda nao aconteceu. Um sinal no ultimo
candle da serie simplesmente nao vira trade - nao ha onde executar.

Duas hipoteses que o engine assume e deixa explicitas:

- **stop e alvo no mesmo candle**: sem tick a tick nao da para saber qual veio
  primeiro. O padrao e' assumir o **stop** (`prioridade_intracandle="stop"`),
  a hipotese pessimista. `"alvo"` e `"nenhuma"` (segura a posicao) tambem
  existem - compare os tres para saber o quanto o resultado depende disso;
- **gap**: se o candle abre alem do nivel, a execucao sai na abertura, nao no
  preco do nivel - contra voce no stop, a favor no alvo.

## Custos

Backtest sem custo e' propaganda. O preco executado nunca e' o do grafico:

| item | efeito |
|---|---|
| `spread_ticks` | metade paga em cada ponta |
| `slippage_ticks` | ordem a mercado sai pior; ordem limitada no alvo nao derrapa (`slippage_no_alvo` liga) |
| `corretagem_fixa` / `corretagem_pct` | por ordem |
| `taxas_b3_pct` | emolumentos + liquidacao, por ponta |

O arredondamento ao tick e' sempre **contra** o trade. Os valores padrao sao
uma referencia conservadora - confirme corretagem e taxas com a sua corretora
antes de tirar conclusao de qualquer numero.

## Horario

`entrada_ate` corta entradas novas no fim do dia e `fechar_em` zera a posicao.
Alem disso, **nenhuma posicao atravessa a noite**: se a serie de um pregao
acaba antes de `fechar_em`, a posicao e' encerrada no ultimo candle do dia -
day trade nao dorme posicionado, e um gap overnight no resultado seria
invencao.

## Risk Manager

Todo trade passa pelo risco: ele dimensiona a posicao, pode recusar o sinal e
para o dia quando um limite estoura. Os motivos ficam em
`resultado.rejeicoes_do_risco`, contados por codigo - e' comum um backtest ter
mais sinais do que trades, e a pagina mostra a diferenca.

## Metricas

Retorno total (R$ e %), numero de trades, win rate, loss rate, payoff,
expectancy (em R$ e em multiplos de R), profit factor, max drawdown (R$ e %),
Sharpe, Sortino e exposicao (tempo em mercado e financeiro medio).

Tudo liquido de custos. Sharpe e Sortino saem de retornos diarios anualizados
por raiz de 252 e viram `None` quando nao ha dados para um numero honesto
(menos de dois dias, desvio zero, nenhum dia negativo no Sortino). Payoff e
profit factor tambem sao `None` quando nao houve perdas - a pagina mostra
`-`, nunca um zero inventado.

## Pagina Backtest

```
python -m cashinho.core.backtest --ativo PETR4 --dias 10 --capital 100000 \
        --timeframe 5m --estrategia baseline-tendencia --risco-trade 0.5 \
        --spread 2 --slippage 1 --corretagem 4.90 --taxas 0.03
python -m cashinho.core.backtest --inicio 2026-08-10 --fim 2026-08-21 --json
```

Mostra curva de capital, drawdown, lista de trades e metricas. A fonte padrao
(`--fonte demo`) gera pregoes sinteticos reproduziveis, para exercitar o
sistema sem depender de dados externos - **nao sao precos reais**. Use
`--fonte csv --pasta dados` para dados exportados da corretora ou
`--fonte yahoo` para tickers `.SA`.

`resultado.para_dict()` entrega tudo em JSON para uma interface grafica.

## O que um backtest nao prova

Resultado passado com uma amostra pequena nao diz nada sobre o futuro. O
engine avisa sozinho quando ha menos de 20 pregoes ou menos de 30 trades, e a
pagina carimba o aviso de estrategia experimental. Trate os numeros como
sanidade da implementacao, nao como promessa.
