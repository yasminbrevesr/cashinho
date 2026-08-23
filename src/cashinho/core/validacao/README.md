# Validacao de estrategias (`cashinho.core.validacao`)

Separa os dados em **TRAIN / VALIDATION / TEST**, compara o desempenho nas
tres particoes e avisa quando ele **cai fora da amostra**. E' a protecao
contra overfitting - nao um otimizador.

```
python -m cashinho.core.validacao --ativo PETR4 --dias 60
python -m cashinho.core.validacao --percentuais 60,20,20 --sem-teste
python -m cashinho.core.validacao --fim-treino 2026-06-30 --fim-validacao 2026-07-31
python -m cashinho.core.validacao --walk-forward --treino 10 --teste 5
```

## A divisao

`DivisaoDeDados` corta a serie **por proporcao** (`por_percentual`) ou **por
data** (`por_data`), sempre em ordem cronologica: treino primeiro, teste por
ultimo. Duas decisoes que parecem detalhe e nao sao:

- o corte acontece **entre pregoes**, nunca no meio de um. Cortar as 14h
  daria a validacao meio dia que ela nao viveu, com posicoes abertas herdadas
  de um periodo que ela nao viu;
- cada janela pode pedir **aquecimento** (`com_aquecimento`) - dias
  anteriores que alimentam medias e ATR mas **nao geram operacao**. Sem isso,
  os primeiros candles de cada particao seriam avaliados com indicadores pela
  metade.

## O cofre: por que o TEST nao e' so uma combinacao

> "Nenhuma otimizacao pode avaliar parametros diretamente sobre o conjunto TEST."

Combinar de nao olhar nao funciona - basta uma espiada para o numero final
deixar de ser out-of-sample. Aqui a regra tem duas partes de codigo:

1. **`CofreDeTeste`** guarda a janela do TEST. `espiar_metadados()` devolve
   periodo e tamanho sem contar nada; `abrir(motivo)` **exige um motivo**, que
   fica no relatorio com o horario. A partir da segunda abertura o cofre se
   declara `contaminado`, e isso vira alerta **critico** no relatorio: o
   resultado final ficou otimista e o relatorio diz isso.
2. **`garantir_sem_teste(particoes)`** e' chamada no inicio de qualquer
   rotina que avalie parametros. Passar `Particao.TEST` levanta
   `TesteProtegidoError`. A selecao chama essa barreira antes de medir
   qualquer candidato.

No fluxo do `ValidadorDeEstrategia`, o cofre e' aberto **uma vez**, no fim,
com a configuracao ja escolhida - e nada do que sair dali volta para ajustar
parametro.

## A selecao: pequena de proposito

`SelecionadorEmTreino` mede os candidatos em TRAIN, filtra por criterios
(minimo de trades, profit factor, retorno positivo) e **escolhe pelo
desempenho em VALIDATION** - nunca pelo do treino, que premia justamente o
mais ajustado ao passado.

A grade e' limitada a `LIMITE_DE_CANDIDATOS` (12). Acima disso levanta
`GradeGrandeDemaisError`. Nao e' limitacao tecnica: com centenas de
combinacoes e um historico curto, o melhor resultado e' quase sempre ruido
bem sorteado, e esta etapa existe para o contrario disso.

## O relatorio e os alertas

`RelatorioDeValidacao` compara as seis medidas pedidas - retorno, drawdown,
profit factor, Sharpe, expectancy e numero de trades - e emite alertas em
tres niveis:

| chave | nivel | quando |
|---|---|---|
| `treino_negativo` | critico | o treino ja perdeu dinheiro: nao ha o que validar |
| `retorno_virou_negativo` | critico | ganhava no treino, perde fora dele |
| `profit_factor_abaixo_de_um` | critico | as perdas passaram os ganhos fora da amostra |
| `expectancy_virou_negativa` | critico | a expectativa por trade virou negativa |
| `teste_contaminado` | critico | o cofre foi aberto mais de uma vez |
| `retorno_caiu` | alerta | sumiu mais da metade do retorno |
| `drawdown_piorou` | alerta | o drawdown fora da amostra e' quase o dobro |
| `expectancy_caiu` / `sharpe_virou_negativo` | alerta | queda nas demais medidas |
| `amostra_pequena` / `treino_sem_amostra` | observacao | poucos trades para concluir |

Os limites ficam em `CriteriosDeDegradacao` e sao configuraveis.

O alerta `treino_negativo` saiu do primeiro relatorio real: com TRAIN em
-0,40% e TEST em +0,19%, o veredito dizia "desempenho se manteve fora da
amostra". Estava certo na aritmetica e errado no sentido - nao ha desempenho
que se sustente quando nao houve desempenho nenhum.

## Walk-forward

Uma divisao unica responde "funcionou naquele pedaco?". O walk-forward
responde "funcionou repetidamente?": treina numa janela, mede na seguinte,
avanca, repete. O que interessa nao e' o melhor ciclo e sim a
**consistencia** - quantos ciclos se sustentaram fora da amostra.

```
 CICLO  TREINO                   FORA DA AMOSTRA        RETORNO  TRADES
 1      21/07-30/07 (-0.4%)      31/07-05/08             +0.19%       1  ✔
 2      27/07-05/08 (+0.5%)      06/08-11/08             -0.16%       1  ✖
 ...
 so 2 de 4 ciclos se sustentaram (50%): o desempenho nao se repete
```

Com menos de 3 ciclos ou menos de 30 trades fora da amostra, o resultado sai
com aviso: a consistencia medida nao significa muita coisa.

## O que este modulo nao faz

- **nao otimiza centenas de parametros** - poucos candidatos, comparados de
  forma explicita;
- **nao promete que a estrategia funciona.** Validacao nao prova acerto: ela
  mostra quando a estrategia **nao** funciona fora do periodo em que foi
  ajustada, que e' a unica das duas coisas que da para saber antes de operar.
