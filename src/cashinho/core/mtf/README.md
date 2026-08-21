# Motor multi-timeframe (`cashinho.core.mtf`)

Alinha as leituras de mercado em varias escalas de tempo e garante que o robo
nunca leia um candle que ainda nao fechou.

## Camadas

A combinacao e' configuracao, nao codigo. O padrao e':

| papel       | timeframe | para que serve                          |
|-------------|-----------|-----------------------------------------|
| `contexto`  | 60m       | viés maior do dia, suportes/resistencias |
| `tendencia` | 15m       | direcao dominante                        |
| `setup`     | 5m        | formacao do setup e niveis de entrada    |
| `gatilho`   | 1m        | momento exato da entrada                 |

Trocar isso e' so passar outro dicionario:

```python
config = MTFConfig(base="1m", camadas={"macro": "1d", "diretor": "30m", "entrada": "3m"})
```

Regras validadas na construcao: cada camada precisa ser multiplo do timeframe
base, `1h` e `60m` sao normalizados para o mesmo rotulo e o papel de menor
timeframe vira automaticamente o `gatilho`.

## Resample ancorado na sessao da B3

Um candle de 60m no pregao brasileiro vai das **10:00 as 11:00**, e nao das
00:00 as 01:00: os baldes sao contados a partir da abertura. O ultimo balde do
dia e' truncado no fechamento (17:00 -> 17:55, nao 18:00), candles fora do
pregao sao descartados e nenhuma barra atravessa a virada do dia.

## A regra critica: sem lookahead

Toda barra carrega a janela que representa (`inicio` inclusivo, `fim`
exclusivo) e so passa a existir para quem consulta quando `fim <= instante`.

```python
engine = MTFEngine(MTFConfig.padrao()).alimentar(serie_1m)
vista = engine.em(agora)          # fotografia do mercado nesse instante

vista.serie_da_camada("tendencia")  # so candles fechados - alimenta indicadores
vista.camada("contexto")            # ultimo 60m fechado
```

Decidindo no 1m as 10:37, o candle de 60m das 10:00 ainda esta em formacao.
Consultar esse candle levanta `LookaheadError` em vez de devolver dados
parciais:

```
LookaheadError: 60m: o candle iniciado em 20/08 10:00 so fecha as 20/08 11:00,
e a consulta foi feita as 20/08 10:37. Usar esse candle agora seria ler o
futuro - espere o fechamento ou use em_formacao('60m') se voce realmente quer
o candle parcial.
```

Isso vale tanto para series reamostradas quanto para series injetadas por um
feed externo (`engine.injetar("60m", serie)`).

Quem precisa mesmo do candle incompleto (acompanhar o candle de gatilho ao
vivo, por exemplo) pede explicitamente com `vista.em_formacao(tf)`.

Uma barra pode estar fechada no relogio e ainda assim ter sido montada com
buracos no feed; nesse caso ela aparece normalmente, porem marcada com
`dados_parciais=True`.

## Backtest

`engine.replay()` percorre a serie base candle a candle e devolve uma vista por
fechamento, o que torna o vazamento de futuro estruturalmente impossivel:

```python
for vista in engine.replay():
    if vista.pronta():
        analisar(vista)
```
