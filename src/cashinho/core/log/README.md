# Log estruturado (`cashinho.core.log`)

```
python -m cashinho.core.log
python -m cashinho.core.log --dia 2026-08-21 --nivel aviso
python -m cashinho.core.log --componente market_data --json
```

```python
from cashinho.core.log import Registrador, Nivel

log = Registrador(pasta="logs", telemetria=monitor.telemetria)
log.aviso("market_data", "fonte lenta", latencia_ms=3200)
```

## Por que ele existe

A revisao tecnica achou o buraco: **zero usos de `logging` no projeto**. A
divergencia entre o Risk Manager e a corretora - a informacao mais importante
que aquela camada tem a dizer - virava uma string em `BrokerComRisco.avisos`,
uma lista em memoria que ninguem lia e que sumia no fim do processo.

## Tres compromissos

1. **Nunca derruba quem chamou.** Log e' observacao, nao operacao: se o disco
   encher no meio do pregao, a ordem sai mesmo assim. Falha de escrita e'
   contada (`falhas_de_escrita`), aparece na tela e **nunca e' levantada**.
2. **Append-only, JSONL, um arquivo por pregao** - o mesmo formato do Diario
   de Trades, que ja se provou.
3. **Alimenta o System Health.** Todo `erro()` vira erro na `Telemetria`, e
   aparece no painel. Antes, um erro so existia se alguem estivesse olhando
   na hora.

## Quatro niveis, com criterio

| nivel | quando |
|---|---|
| `DEBUG` | rastro para entender uma decisao depois (desligado por padrao) |
| `INFO` | vale estar no historico do pregao - ordem enviada, varredura concluida |
| `AVISO` | saiu do esperado e o robo seguiu - agenda velha, fonte lenta, divergencia reconciliada |
| `ERRO` | falhou. Alguem precisa olhar |

**Nao ha `CRITICO`.** No Cashinho, o que e' critico nao vira nivel de log,
vira **bloqueio**: kill switch, `NAO OPERAR`, `BrokerComSaude`. Um log mais
vermelho nao para operacao nenhuma.

O limiar e' global e por componente: `niveis_por_componente={"market_data":
Nivel.DEBUG}` liga o rastro fino de um componente sem inundar o resto.

## Dados junto da mensagem

```python
log.aviso("paper_broker", "ordem recusada", symbol="PETR4", necessario=3000.9)
```

Gravar so texto responde "o que houve". Gravar os dados junto responde
"quantas vezes o saldo barrou PETR4 este mes" - o log fica **consultavel**,
nao so legivel.

## Onde ja esta ligado

| componente | o que registra |
|---|---|
| `BrokerComRisco` | divergencia risco x corretora (ERRO), ordem barrada (AVISO) |
| `PaperBroker` | kill switch, ordem recusada |
| `RiskManager` | kill switch, com o P&L do dia junto |
| `ScannerB3` | falha de dado por ativo |

Em todos, o log e' **parametro opcional** (`log=None`). Sem ele, o
`RegistradorNulo` engole tudo e o comportamento e' identico ao de antes - a
instrumentacao nao pode alterar quem nao pediu log.

## Leitura

`ler()` devolve `(eventos, linhas_descartadas)`. Linha corrompida nao derruba
a leitura **e nao some**: volta com o motivo, para a tela mostrar. Arquivo
inexistente nao e' linha corrompida - sao coisas diferentes e a tela diz
coisas diferentes.
