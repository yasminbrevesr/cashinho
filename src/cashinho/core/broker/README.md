# Broker e Paper Trading (`cashinho.core.broker`)

Uma interface `Broker` independente e uma corretora simulada que a implementa.

```python
from cashinho.core.broker import BrokerComRisco, Order, OrderType, PaperBroker
from cashinho.core.risk import RiskManager

broker = BrokerComRisco(PaperBroker(), RiskManager())
broker.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 500,
                         stop_referencia=30.70))
```

## A interface

`place_order()` · `cancel_order()` · `get_orders()` · `get_positions()` ·
`get_balance()` — mais `get_trades()` e `cancel_all()` com implementacao
padrao. O PaperBroker implementa simulando; uma ligacao com a corretora de
verdade implementaria o mesmo contrato, e quem chama nao veria diferenca.

## O que o PaperBroker simula

| tipo | comportamento |
|---|---|
| `market` | executa na hora, no ultimo preco conhecido |
| `limit` | executa quando o preco alcanca o limite (gap executa melhor) |
| `stop` | dispara e vira mercado (gap executa pior) |
| `stop_loss` | protecao de posicao aberta; exige posicao |
| `take_profit` | realizacao de posicao aberta |
| `oco` | par ligado: quando um executa, o outro e' cancelado |

E leva a serio: **spread e slippage** (o preco executado nunca e' o do
grafico), **taxas** nas duas pontas, **saldo** (compra que nao cabe no caixa
e' rejeitada), **quantidade** e **posicao existente** — venda sobre compra
reduz e registra a operacao, venda maior que a posicao inverte o lado, e
compra sobre compra faz preco medio.

Quando stop e alvo cabem no mesmo candle, o stop vem primeiro
(`prioridade_intracandle`) — a mesma hipotese pessimista do Backtest Engine.

Uma diferenca deliberada em relacao ao backtest: aqui a ordem a mercado
executa **na hora**, porque e' isso que acontece quando alguem clica em
comprar. No backtest ela espera a abertura do candle seguinte, porque la a
decisao foi tomada com o candle ja fechado.

## A trava: toda ordem passa pelo Risk Manager

`BrokerComRisco` embrulha **qualquer** `Broker` e implementa a mesma
interface. Ordem de entrada so chega na corretora depois de o risco aprovar, e
**com a quantidade que o risco autorizou** — pediu 100.000, o risco liberou
3.225, vao 3.225. Pedido menor que o autorizado e' respeitado.

Duas decisoes que valem explicacao:

- ordem **sem stop de referencia** e' rejeitada na porta: sem stop nao ha
  risco por acao, e sem risco por acao nao ha dimensionamento;
- ordem que **reduz** posicao (stop loss, take profit, encerramento) passa
  direto, inclusive com o risco travado. Uma trava que impede de sair de uma
  posicao aberta seria pior do que trava nenhuma.

O que executa e' espelhado no Risk Manager, com a quantidade **executada** -
nao a autorizada. Sem isso a exposicao viraria ficcao: uma compra de 100 com
3.225 aprovadas registraria R$ 100 mil de exposicao onde ha R$ 3,1 mil.

## Pagina Paper Trading

```
python -m cashinho.core.broker                       # a pagina
python -m cashinho.core.broker preco PETR4 31.00     # o mercado anda
python -m cashinho.core.broker comprar PETR4 500 --stop 30.70
python -m cashinho.core.broker oco PETR4 500 --stop 30.70 --alvo 31.60
python -m cashinho.core.broker kill-switch on --motivo "fim do expediente"
```

Mostra saldo, patrimonio, posicoes marcadas a mercado, ordens abertas, ordens
barradas com o motivo, operacoes encerradas e P&L do dia e acumulado. O estado
da conta simulada fica em `~/.cashinho`.

## KILL SWITCH

```
╔══════════════════════════════════════════════════════════════════╗
║        KILL SWITCH ACIONADO - NOVAS OPERACOES BLOQUEADAS         ║
╚══════════════════════════════════════════════════════════════════╝
```

Trava dos dois lados na hora: o Risk Manager para de aprovar e a corretora
para de aceitar. Ordens pendentes de **abertura** sao canceladas — senao
"imediatamente" seria mentira, elas continuariam executando. Ordens de
**protecao** (stop loss e take profit) continuam valendo, e ordens que reduzem
posicao continuam permitidas: a trava impede abrir, nao sair.
