# Market Replay (`cashinho.core.replay`)

Reproduz um pregao candle a candle, rodando o pipeline inteiro **como se
fosse ao vivo**.

```
python -m cashinho.core.replay --ativo PETR4 --data 2026-08-20 --velocidade 10x
python -m cashinho.core.replay --listar-dias
python -m cashinho.core.replay --velocidade maxima --acompanhar 60
```

Voce escolhe **ativo**, **data**, **timeframe** e **velocidade** (1x, 5x, 10x,
60x ou maxima). Em 1x o replay espera o tempo real entre candles; em maxima,
roda sem pausa.

## O caminho, a cada candle

```
fita -> multi-timeframe -> Strategy -> Opportunity -> Score
     -> Auditor -> Risk Manager -> Paper Broker
```

Cada candle que fecha dispara o pipeline com **apenas o que existia naquele
instante**. Uma operacao aprovada vira ordem no Paper Broker, com OCO de
protecao, e a saida cai no Diario de Trades.

## Contra look-ahead: tres barreiras

1. **A fita** (`FitaDeMercado`) guarda a serie mas nao entrega nada alem da
   posicao atual. Pedir um candle a frente levanta `LookaheadError`, e nao ha
   metodo para ver o futuro - nao e' disciplina de quem chama, e' ausencia de
   caminho.
2. **A vista multi-timeframe** so devolve barras ja fechadas no instante
   consultado - a garantia que o motor de alinhamento carrega desde sempre.
3. **O Paper Broker** recebe **um** candle por vez, o atual, nunca a serie.

### O teste decisivo

Os testes de fita e de camada sao necessarios mas nao suficientes: eles
verificam a estrutura. O que prova o resultado e' outro:

> para varios instantes do replay, um `OpportunityEngine` **limpo**, recebendo
> a serie **truncada exatamente naquele candle**, chega ao mesmo estado, ao
> mesmo score e ao mesmo preco de entrada.

Se qualquer componente estivesse espiando adiante, o replay - que carrega a
serie inteira na memoria - decidiria diferente do engine que so viu o passado.
O teste falha ruidosamente se alguem introduzir um vazamento.

## O grafico

```
    R$ 28,13 ┤        ██▒│                     S                        │█  S R$ 28,13
    R$ 28,01 ┤                                 s█▒██│ │▒█
    R$ 27,99 ┤                                 E ││     │                  E R$ 27,99
  █ alta  ▒ baixa  s sinal  E entrada  S stop  A alvo  X saida
```

Cada coluna e' um candle - corpo cheio na alta, vazado na baixa, pavio fino.
Por cima entram os marcadores do que o pipeline decidiu, e os niveis de
entrada, stop e alvo ganham rotulo a direita. So o que ja passou e' desenhado.

## A tela

Cabecalho com as quatro escolhas, barra de progresso, grafico, contagem do
pipeline (sinais, oportunidades, barrados no auditor, barrados no risco,
entradas, saidas), conta (patrimonio, caixa, P&L, posicao aberta) e os
ultimos eventos.

`--acompanhar N` redesenha a tela a cada N candles e sempre que algo acontece.
