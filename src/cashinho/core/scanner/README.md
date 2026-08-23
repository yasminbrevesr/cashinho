# Scanner B3 (`cashinho.core.scanner`)

Varre uma watchlist com o pipeline inteiro e ranqueia o que sobrou.

```python
from cashinho.core.scanner import ScannerB3, ScannerConfig
from cashinho.data.synthetic import SyntheticProvider

scanner = ScannerB3(SyntheticProvider(), ScannerConfig(watchlist=("PETR4", "VALE3")))
resultado = scanner.varrer()

resultado.tem_oportunidades     # False e' um resultado valido
resultado.ranking("score")      # a watchlist ordenada
```

## As oito etapas, por ativo

```
Market Data -> Context -> Multi-Timeframe -> Strategy -> Opportunity
            -> Score -> Auditor -> Risk Manager
```

As tres primeiras sao do scanner (buscar, filtrar, alinhar); as cinco ultimas
sao o `Pipeline` que ja existia. Cada ativo carrega a trilha inteira, entao a
coluna **Status** responde onde ele parou - a pergunta que mais importa quando
nada foi liberado.

## Filtros iniciais

Rodar o pipeline em vinte ativos custa tempo. Estes filtros olham so a serie
bruta e cortam antes:

| filtro | corta quando |
|---|---|
| disponibilidade de dados | serie curta ou defasada (`atraso_maximo_minutos`) |
| liquidez | financeiro medio por pregao abaixo de `liquidez_minima_diaria` |
| volume | volume recente abaixo de `volume_relativo_minimo` da media do ativo |
| volatilidade | ATR fora da faixa `atr_min_pct`–`atr_max_pct` |
| spread | acima de `spread_maximo_ticks` — **so quando informado** |

Como no auditor, ha tres respostas: passou, cortou e **nao verificado**. A
serie de candles nao carrega bid/ask, entao sem book o spread sai como nao
verificado - o scanner nao inventa um spread confortavel. Informe com
`varrer(spreads={"PETR4": 1.0})` quando tiver o dado.

## Ranking

Ordenavel por `score` (padrao), `rr`, `risco`, `ativo` ou `status`. O score
usado e' o **pos-auditoria**, ja com os descontos. `apenas_operaveis=True`
mostra so o que esta liberado ou aguardando gatilho.

```
  ATIVO    SCORE  SETUP                DIR     STATUS             TF    R:R      RISCO  HORA
  ITUB4     65.9  5m: pullback         VENDA   SETUP REJEITADO    5m   0.68  R$0,11/ac  17:55
  PETR4     62.4  5m: failed_breakout  COMPRA  AGUARDANDO GATILHO 5m   2.00  R$0,12/ac  17:55
```

## Nenhuma oportunidade nao e' erro

Na maior parte do pregao, varrer e nao achar nada e' o resultado **esperado**.
A tela mostra a faixa `NENHUMA OPORTUNIDADE ENCONTRADA` com os motivos ativo a
ativo, e o CLI sai com **codigo 0** - codigo diferente de zero fica reservado
para falha de verdade (fonte inacessivel, configuracao invalida).

## Um Risk Manager para a varredura inteira

Perda diaria, numero de trades e exposicao sao limites da **carteira**, nao do
ativo. Como o scanner apenas avalia (nao abre posicao), a ordem dos ativos nao
muda o resultado - mas abrir uma das oportunidades muda o que sobra para as
outras.

## Isolamento entre ativos

Os engines de confluencia, oportunidade e auditoria guardam cache por candle
para nao recalcular estrutura a cada tick. Numa varredura, dois ativos tem o
mesmo timeframe, o mesmo horario de fechamento e o mesmo tamanho de serie -
por isso o **symbol faz parte da chave de cache**. Sem ele, um ativo lia a
estrutura do outro. Um teste compara a varredura conjunta com a analise ativo
a ativo e exige resultados identicos.

## Linha de comando

```
python -m cashinho.core.scanner
python -m cashinho.core.scanner --ativos PETR4,VALE3,ITUB4 --ordenar rr --operaveis
python -m cashinho.core.scanner --detalhe PETR4      # a trilha das oito etapas
python -m cashinho.core.scanner --json > varredura.json
```
