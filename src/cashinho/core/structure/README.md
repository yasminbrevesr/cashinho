# Estrutura de preco (`cashinho.core.structure`)

Le o grafico do jeito que um trader le - topos, fundos, tendencia, zonas e
Fibonacci - mas com criterios mecanicos, verificaveis em teste.

```python
from cashinho.core.structure import analisar_estrutura, painel, grafico

estrutura = analisar_estrutura(serie_5m)
print(painel(estrutura))
print(grafico(serie_5m, estrutura))
```

Com o motor multi-timeframe, a leitura sai automaticamente livre de lookahead
(a vista so entrega candles fechados):

```python
from cashinho.core.structure import analisar_camada

estrutura = analisar_camada(engine.em(agora), "setup")
```

## Vocabulario

| termo | definicao objetiva |
|---|---|
| **pivo** | candle cuja maxima (ou minima) nao e' superada por `pivo_esquerda` candles antes nem por `pivo_direita` depois |
| **swing high / swing low** | pivo que sobreviveu ao filtro de ruido (perna >= `swing_min_atr` ATR ou `swing_min_pct` do preco) |
| **topo / fundo** | o swing high e o swing low mais recentes - os que definem a leitura atual |
| **perna (swing)** | trecho entre dois swings alternados |
| **swing valido** | perna acima do limiar: a unica coisa que autoriza desenhar Fibonacci |

Um pivo carrega `indice_confirmacao`: com 2 candles de confirmacao, o topo das
10:30 so existe as 10:40. Nenhuma leitura enxerga um pivo antes disso.

## Tendencia

Regra unica, com tolerancia em ATR para nao contar centavos como estrutura:

- **alta**: topo mais alto **e** fundo mais alto (HH/HL);
- **baixa**: topo mais baixo **e** fundo mais baixo (LH/LL);
- **lateralizacao**: todo o resto - inclusive HH/LL (expansao) e LH/HL
  (compressao/triangulo), que ficam explicitos na descricao.

## Suporte e resistencia

Nivel e' faixa, nao linha: pivos dentro de `tolerancia_nivel_atr` ATR viram a
mesma zona. A forca (0..1) combina numero de toques, recencia, proeminencia
dos pivos e um bonus quando a zona ja funcionou como suporte **e** como
resistencia.

## Eventos

- **rompimento**: o candle FECHA alem da zona por pelo menos
  `rompimento_min_atr` ATR **vindo do outro lado** (e' cruzamento; uma zona
  que sempre esteve abaixo do preco nao e' "rompida" a cada candle);
- **possivel falso rompimento**: rompeu e voltou para dentro em ate
  `falso_rompimento_janela` candles, ou a sombra furou e o candle fechou de
  volta (rejeicao). E' "possivel" de proposito - so o proximo candle confirma;
- **pullback**: correcao contra a tendencia dentro da perna valida, entre
  `pullback_min` e `pullback_max`, sem devolver a origem.

## Fibonacci

Nunca desenhado a esmo: sem swing valido, `estrutura.fib is None` e
`motivo_sem_fib` diz por que. Havendo swing, a ancoragem e' **0% no extremo**
da perna e **100% na origem**.

Retracoes: **23,6% · 38,2% · 50% · 61,8% · 78,6%**
Extensoes: **127,2% · 161,8%**

Zonas (continuas na faixa de pullback, para que toda correcao caia em exatamente uma):

| zona | faixa | leitura |
|---|---|---|
| rasa | 23,6% - 38,2% | tendencia forte, entrada agressiva |
| nobre | 38,2% - 61,8% | melhor relacao risco/retorno |
| profunda | 61,8% - 78,6% | ainda valida, exige confirmacao |
| alvos | 127,2% - 161,8% | projecao da perna |

Cada nivel marca **confluencia** quando cai dentro de uma zona de suporte ou
resistencia - o sinal que mais interessa na hora de escolher a entrada.

## Interface

- `resumo(estrutura)` - uma linha por ativo, para varrer a watchlist;
- `painel(estrutura)` - pivos, S/R, Fibonacci e eventos em texto;
- `grafico(serie, estrutura)` - grafico ASCII com pivos (`▲`/`▼`), zonas de
  S/R e zonas de Fibonacci sombreadas; cada camada pode ser desligada
  (`mostrar_pivos`, `mostrar_niveis`, `mostrar_fib`);
- `estrutura.para_dict()` - o mesmo conteudo em JSON, para uma interface
  grafica consumir.

## Ajustes

Todos os limiares estao em `EstruturaConfig` - nenhum numero magico espalhado
pelo codigo:

```python
from cashinho.core.structure import EstruturaConfig, analisar_estrutura

cfg = EstruturaConfig(pivo_esquerda=3, pivo_direita=3, swing_min_atr=1.5)
estrutura = analisar_estrutura(serie_15m, cfg)
```
