# Multi-Timeframe Engine (`cashinho.core.confluencia`)

Le contexto, tendencia, setup e gatilho no mesmo instante e - so quando uma
regra configurada fecha por inteiro - cria uma `Opportunity`.

O engine tem duas metades, em modulos separados de proposito:

| metade | onde | responsabilidade |
|---|---|---|
| **alinhamento** | `cashinho.core.mtf` | quais candles ja fecharam em cada timeframe naquele instante; levanta `LookaheadError` se alguem tentar ler um que nao fechou |
| **leitura e regras** | este modulo | o que cada camada significa e quando a combinacao autoriza uma oportunidade |

```python
from cashinho.core.confluencia import MultiTimeframeEngine

engine = MultiTimeframeEngine()                 # 60m/15m/5m/1m
mtf = engine.alimentar(serie_1m)
resultado = engine.avaliar(mtf.agora(), "PETR4")

resultado.leitura.context.estado                # ContextState.BULLISH
resultado.oportunidade                          # None ate uma regra fechar
```

## As quatro camadas

Quatro tipos distintos, nao quatro strings: uma regra que pede `Setup` nao
aceita um `Trigger` por engano.

| camada | timeframe padrao | estados |
|---|---|---|
| `Context` | 60m | `bullish` · `bearish` · `neutral` |
| `Trend` | 15m | `bullish` · `bearish` · `sideways` |
| `Setup` | 5m | `pullback` · `breakout` · `failed_breakout` · `range_edge` · `none` |
| `Trigger` | 1m | `breakout_with_volume` · `ma_reclaim` · `rejection_wick` · `none` |

A combinacao e' configuravel - e' so passar outro `MTFConfig`:

```python
MultiTimeframeEngine(MTFConfig(base="1m", camadas={
    "context": "30m", "trend": "10m", "setup": "2m", "trigger": "1m",
}))
```

## Tres instantes, nunca confundidos

Toda camada carrega:

- `ts` - abertura do candle que gerou a leitura;
- `fechado_em` - quando esse candle fechou (a partir daqui a leitura vale);
- `lido_em` - o instante da consulta.

`fechado_em <= lido_em` e' verificado na construcao: um `Camada` com candle do
futuro **nao consegue existir**. E todas as camadas de uma leitura precisam ter
o mesmo `lido_em`, senao `LeituraMultiTimeframe` recusa.

Disso sai a coluna de **idade** na tela: as 12:37, o contexto de 60m e' o
candle das 12:00 - tem 37 minutos. A tela mostra isso em vez de dar a
impressao de que as quatro camadas sao igualmente recentes. Uma regra pode
exigir frescor com `idade_maxima_minutos={"context": 60}`.

Faltar dado nao e' o mesmo que estar neutro: uma camada sem candle fechado
entra em `leitura.faltando` e **nenhuma regra que a exige pode ser
satisfeita**.

## Regras

Uma regra e' a lista de estados aceitos por papel. So fecha quando todos
batem - nao existe "quase". O exemplo do enunciado e' a primeira do conjunto
padrao:

```
60m: context = bullish
15m: trend   = bullish
 5m: setup   = pullback
 1m: trigger = breakout_with_volume
```

```python
RegraOportunidade(
    nome="pullback a favor da tendencia",
    context=(ContextState.BULLISH, ContextState.BEARISH),
    trend=(TrendState.BULLISH, TrendState.BEARISH),
    setup=(SetupState.PULLBACK,),
    trigger=(TriggerState.BREAKOUT_WITH_VOLUME, TriggerState.MA_RECLAIM),
    exigir_vies_alinhado=True,
    confianca_minima=0.5,
)
```

**Uma invariante nao pode ser desligada por regra nenhuma**: setup e gatilho
precisam apontar para o mesmo lado. O gatilho e' o que coloca a operacao na
rua - se ele vai para o lado oposto do setup, nao ha entrada coerente,
mesmo com `exigir_vies_alinhado=False`.

A avaliacao guarda cada checagem, inclusive as que falharam, para a tela
poder dizer *por que* nao houve oportunidade.

## Na tela Analise

A secao `ANALISE MULTI-TIMEFRAME` mostra o estado de cada periodo, o vies, a
forca, quando fechou e ha quanto tempo, mais o alinhamento e o placar das
regras:

```
 ANALISE MULTI-TIMEFRAME
   camada    TF    estado                 vies      forca  fechou  idade
   context   60m   bullish                ▲ alta    ████·  12:00   37 min
   trend     15m   bullish                ▲ alta    ███··  12:30   7 min
   setup     5m    pullback               ▲ alta    ████·  12:35   2 min
   trigger   1m    breakout_with_volume   ▲ alta    █████  12:37   agora

   alinhamento: as camadas apontam para bullish

   REGRAS DE CONFLUENCIA
   ✔ pullback a favor da tendencia  (confianca 82%)
   ✖ rompimento com contexto — setup: pullback (esperado breakout)
```

A secao aparece sozinha quando o sinal traz uma leitura anexada
(`Signal.extras["multitimeframe"]`); a tela nao importa este modulo, so sabe
desenhar o que ele anexa.

## Integracao

`EstrategiaConfluencia` embrulha o engine como uma `Strategy` comum, entao a
confluencia entra na tela Analise, no Risk Manager, no backtest e na
comparacao de timeframes sem que nenhuma dessas pecas conheca este modulo.
