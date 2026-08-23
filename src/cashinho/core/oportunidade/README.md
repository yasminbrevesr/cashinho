# Opportunity Engine e sistema de score (`cashinho.core.oportunidade`)

Transforma a leitura multi-timeframe em uma oportunidade **pontuada, com
prazo e com estado**.

```python
from cashinho.core.oportunidade import OpportunityEngine, pagina_oportunidade

engine = OpportunityEngine()
mtf = engine.alimentar(serie_1m)
op = engine.avaliar(mtf.agora(), "PETR4")

print(pagina_oportunidade(op))
```

O engine sempre devolve uma `Opportunity`, inclusive quando nao ha o que
fazer - silencio nao explica nada, `NAO OPERAR` com o motivo, sim. Mas so o
estado `SETUP APROVADO` e' acionavel.

## A oportunidade

`symbol` · `timestamp` · `direction` · `setup` · `score` · `entry` · `stop` ·
`target` · `risk_reward` · `timeframe_context` · `timeframe_trend` ·
`timeframe_setup` · `timeframe_trigger` · `reasons` · `warnings` ·
`invalidation` · `expires_at`

Mais `estado`, `score_detalhado`, `leitura` (as quatro camadas) e
`motivo_do_estado`. Nao tem quantidade: dimensionar e' do Risk Manager.

## Estados

| estado | quando |
|---|---|
| `SETUP APROVADO` | regra fechou, score acima do minimo, RR acima do minimo e nenhum componente critico abaixo do piso |
| `AGUARDANDO GATILHO` | o setup esta pronto e a unica pendencia da regra e' o gatilho |
| `SETUP REJEITADO` | ha setup, mas ele nao passa nos criterios |
| `NAO OPERAR` | camadas faltando, sem direcao ou serie curta demais |
| `EXPIRADO` | `expires_at` ficou para tras (`op.estado_em(agora)`) |

`expires_at` = `timestamp` + `expiracao_candles_gatilho` candles do timeframe
de gatilho (3 por padrao). O registro original nao muda com o tempo:
`op.estado` guarda o que foi decidido, `op.estado_em(agora)` aplica o relogio.

## O score, de 0 a 100

Onze componentes, cada um com nota 0-100 **e a frase que a justifica**:

| componente | peso padrao | | componente | peso padrao |
|---|---|---|---|---|
| Tendencia | 1.5 | | Volume | 1.0 |
| Estrutura | 1.3 | | Suporte/Resistencia | 1.0 |
| Qualidade do gatilho | 1.3 | | Momentum | 0.9 |
| Risco/Retorno | 1.3 | | VWAP | 0.9 |
| Medias | 1.0 | | Fibonacci | 0.7 |
| | | | Volatilidade | 0.7 |

Os pesos **nao precisam somar 1** - sao normalizados pela soma, entao da para
dizer "tendencia pesa o dobro de fibonacci" sem recalcular o resto. Peso zero
desliga o componente.

```python
from cashinho.core.oportunidade import OpportunityEngine, PESOS_PADRAO

engine = OpportunityEngine(pesos=PESOS_PADRAO.atualizar(vwap=2.0, fibonacci=0.0))
```

### Nada de caixa-preta

Todo componente carrega `nota`, `peso`, `contribuicao` e `leitura`. A tela
mostra os onze - inclusive os que puxaram para baixo:

```
 SCORE
   Qualidade do gatilho  ██████████    99   peso 1.3  contribui  11.1
                         └ breakout_with_volume: fechou acima da maxima do candle anterior com 1.76x o volume
   Tendencia             ████······    45   peso 1.5  contribui   5.8
                         └ 15m sem direcao definida; contexto 60m neutro
   Suporte/Resistencia   ··········     0   peso 1.0  contribui   0.0
                         └ 0.5 ATR ate a resistencia de R$ 30,68; o ALVO passa por dentro dela
   ──────────────────────────────────────────────────────────────────
   SCORE FINAL           ██████····    62
```

### Pisos: a media nao pode enterrar uma falha critica

Uma media ponderada deixa um componente terrivel ser voto vencido. O exemplo
acima e' real: score 62 com o alvo atravessando uma resistencia colada na
entrada. Por isso ha pisos por componente (`notas_minimas`), e abaixo deles o
setup e' **rejeitado por mais alto que esteja o score**:

```python
ConfigOportunidade(notas_minimas={"gatilho": 30, "risco_retorno": 25,
                                  "suporte_resistencia": 20})
```

O alvo tambem passou a ser limitado pela primeira zona contraria: nao adianta
projetar 2R do outro lado de uma parede. Sem espaco, o RR cai e o setup e'
rejeitado - que e' a leitura honesta da situacao.

## Integracao

`EstrategiaOportunidade` embrulha o engine como uma `Strategy` comum, entao a
oportunidade pontuada entra na tela Analise (o painel de score aparece junto
com a secao multi-timeframe), no Risk Manager, no backtest e na comparacao de
timeframes sem que nenhuma dessas pecas conheca este modulo.
