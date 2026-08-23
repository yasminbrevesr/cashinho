# Diario de Trades (`cashinho.core.diario`)

Registra sozinho cada operacao encerrada no Paper Broker e resume o
resultado por setup, ativo, horario, dia da semana e timeframe.

> ## Sem IA nesta etapa
>
> As estatisticas sao contagem, soma e divisao - operacoes que voce refaz na
> mao e chega no mesmo numero. Nada aqui sugere mudanca de estrategia nem
> ajusta parametro sozinho. Um teste percorre a arvore de sintaxe do modulo
> garantindo que ele nao importa nem biblioteca de IA nem `random`, e outro
> confirma que a mesma amostra em qualquer ordem da o mesmo resultado.
>
> **O diario mede; quem decide e' voce.**

## Registro automatico

`BrokerComDiario` embrulha qualquer `Broker` e implementa a mesma interface.
Toda operacao encerrada vira registro - sem ninguem precisar lembrar de
anotar.

```python
from cashinho.core.diario import BrokerComDiario, DiarioDeTrades

broker = BrokerComDiario(paper_broker, DiarioDeTrades(), arquivo="diario.jsonl")
broker.anotar_contexto("PETR4", oportunidade=op, auditoria=auditoria)
...                                     # opera normalmente
broker.diario.registros                 # ja registrado
```

No Paper Trading isso ja esta ligado: `python -m cashinho.core.broker`
alimenta `~/.cashinho/diario.jsonl` a cada operacao encerrada.

## As duas metades de um registro

| o que a corretora sabe | o que a analise dizia |
|---|---|
| data, horario, ativo, direcao | setup, score, timeframes |
| entrada, saida, quantidade | stop, alvo, motivo da entrada |
| resultado, custos | condicoes do mercado, warnings do auditor |
| motivo da saida | |

A segunda metade vem de `anotar_contexto()`, chamado **antes** da entrada.
Sem ela o registro entra assim mesmo, so que sem o porque - melhor um diario
incompleto do que um trade perdido. Risco e R:R sao derivados: risco =
quantidade x distancia ate o stop, e `resultado_em_r` deixa o resultado
comparavel entre ativos de precos diferentes.

O contexto e' guardado como **fatos**, nao objetos, entao sobrevive ao fim do
processo - o caso normal de quem opera por varias chamadas de linha de
comando.

## Filtros e estatisticas

```
python -m cashinho.core.diario
python -m cashinho.core.diario --ativo PETR4 --resultado perdedor
python -m cashinho.core.diario --setup pullback --de 2026-08-01 --ate 2026-08-31
python -m cashinho.core.diario --grupos setup,horario --limite 10
python -m cashinho.core.diario --detalhe reg-abc123
```

Filtros: ativo, setup (trecho do nome), timeframe, periodo, resultado
(vencedor/perdedor/zerado) e direcao - combinaveis.

Cinco visoes: **por setup**, **por ativo**, **por horario de entrada**, **por
dia da semana** e **por timeframe**. Cada uma com n, win rate, payoff, profit
factor, expectancy, R medio e total.

## Honestidade dos numeros

- payoff e profit factor viram `-` quando nao houve perdas: razao infinita
  nao vira numero bonito;
- grupos com menos de 20 operacoes levam `*` e a tela avisa que o numero diz
  pouco - com quatro trades, "100% de acerto" nao significa nada.

## Formato

JSONL: uma operacao por linha, novas linhas so entram no fim, registro antigo
nunca e' reescrito. Linha corrompida e' ignorada na leitura sem derrubar o
resto do diario.
