# System Health (`cashinho.core.saude`)

O painel que responde uma pergunta so: **da para operar agora?**

```
python -m cashinho.core.saude
python -m cashinho.core.saude --fonte yahoo --ativo PETR4
python -m cashinho.core.saude --diario diario.jsonl --eventos eventos.json
python -m cashinho.core.saude --json    # codigo de saida 2 quando bloqueado
```

Sete componentes, tres estados:

```
  COMPONENTE       ESTADO        ULTIMO SINAL  LATENCIA   ERROS
  Market Data      ○ OFFLINE         14:08:00     380ms       -
                   └ ultimo dado ha 22 min, acima do limite de 15 min
  Database         ● ONLINE          14:30:00         -       -
  Scanner          ◐ DEGRADED               -         -       -
  Paper Broker     ● ONLINE                 -         -       -
                   └ [simulado] patrimonio R$ 100.000,00 · 0 ordem(ns) aberta(s)
  News             ○ OFFLINE                -         -       -
  Backtest Engine  ◐ DEGRADED               -         -       -
  Risk Manager     ● ONLINE                 -         -       -
                   └ [TRADING LIBERADO] 0 trade(s) hoje · P&L +0,00
```

Mais o bloco do sistema: **estado geral, modo atual, kill switch e horario da
ultima analise**; e a lista de **erros recentes**, com hora e componente.

## A regra que sai da tela e vira trava

> Se o Market Data estiver OFFLINE ou desatualizado, operacoes novas devem ser
> bloqueadas.

Mostrar OFFLINE numa tela e deixar a ordem passar seria decorar o problema.
Por isso a regra tem duas partes:

1. `SaudeDoSistema.bloqueia_novas_operacoes` - derivado de uma **lista de
   motivos** montada por regra explicita, nao de um `if` escondido na tela;
2. **`BrokerComSaude`** - embrulha qualquer corretora e **recusa ordem de
   abertura** enquanto o bloqueio valer. Empilha com `BrokerComRisco` e
   `BrokerComDiario`.

Como no `BrokerComRisco`, **ordem que reduz posicao passa sempre**. Uma trava
que impede de sair de uma posicao aberta e' pior que trava nenhuma - e com o
feed caido, sair e' justamente o que mais se quer poder fazer.

Kill switch acionado (no Risk Manager **ou** no botao do Paper Broker) tambem
entra na lista de bloqueios. Sao dois lugares diferentes que param o robo, e
um painel que mostrasse so um deles estaria mentindo na metade das vezes.

## Atraso alem do tolerado nao e' ressalva, e' queda

Para o Market Data, DEGRADED e OFFLINE tem significados distintos:

| situacao | estado | bloqueia? |
|---|---|---|
| dado de ate 3 min | ONLINE | nao |
| dado de 3 a 15 min | DEGRADED | nao (feed gratuito atrasa; travar nisso travaria o robo o dia todo) |
| dado com mais de 15 min | **OFFLINE** | **sim** |
| nenhum dado recebido | **OFFLINE** | **sim** |

Os limiares ficam em `LimiaresSaude` e a lista de estados que bloqueiam, em
`ConfigSaude.bloqueia_em` - quem quiser exigir Market Data impecavel inclui
`DEGRADED` ali.

### O relogio de mercado fechado

As 20h de uma sexta, o ultimo candle e' das 17h55 - e isso e' o certo, nao uma
falha. Fora do pregao o atraso e' medido ate o **fechamento da ultima sessao**,
nao ate agora. Mas um candle de tres semanas atras nao fica em dia so porque
hoje e' domingo: a conta procura o pregao mais recente que ja terminou, e o
buraco aparece.

E o instante anotado e' o **fechamento** do candle, nao a abertura - anotar a
abertura embutiria um atraso fantasma do tamanho do timeframe, e todo feed de
5m viveria DEGRADED sem motivo.

## Quem trabalha anota; o painel so mostra

As sondas nao adivinham latencia nem erro: elas leem a `Telemetria`, onde os
componentes anotam o que fizeram.

```python
telemetria.sucesso("market_data", latencia_ms=380, dado_em=fechamento_do_candle)
telemetria.erro("news", "timeout ao ler a agenda")
monitor.registrar_analise()
```

**Silencio nao vira ONLINE.** Componente que nunca reportou aparece OFFLINE
dizendo exatamente isso - o painel existe para mostrar o que nao esta
funcionando, e "nunca deu sinal" e' uma das formas de nao funcionar. A unica
excecao sao os componentes marcados como opcionais (Scanner e Backtest
Engine): sem uso na sessao, ficam DEGRADED com "nunca usado", porque nao ter
rodado um backtest nao e' defeito.

Latencia e' a **mediana** das ultimas medicoes: uma leitura ruim nao vira
alarme.

## O que este modulo nao faz

- **nao conserta nada.** Ele mostra, e bloqueia o que precisa ser bloqueado;
- **nao inventa saude.** Componente sem conexao aparece OFFLINE com o motivo,
  nunca omitido da lista;
- **nao decide estrategia.** A unica decisao que ele toma e' se a porta da
  corretora esta aberta para ordem nova.
