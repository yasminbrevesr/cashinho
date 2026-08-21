# Estrategias (`cashinho.core.strategy`)

> ⚠ **A estrategia que existe hoje (`baseline-tendencia`) foi escrita para
> VALIDAR A ARQUITETURA, nao para operar.** As regras sao propositalmente
> simples e obvias, nao passaram por otimizacao nem por backtest, e nao
> representam uma estrategia final de day trade. Ela serve para provar que as
> pecas se encaixam - e para ser substituida.

## O contrato

Uma estrategia recebe `StrategyContext` e devolve `Signal`. So isso. Ela nao
envia ordem, nao dimensiona posicao e nao conhece o Risk Manager.

```python
from cashinho.core.strategy import BaselineTendenciaVolumeATR, StrategyContext, tela_analise

sinal = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_5m))
print(tela_analise(sinal))
```

### Signal

| campo | o que e' |
|---|---|
| `symbol` | ativo |
| `timestamp` | fechamento do candle a que o sinal se refere |
| `timeframe` | timeframe da leitura |
| `action` | `BUY`, `SELL`, `WAIT` ou `NONE` |
| `setup` | nome curto da condicao encontrada |
| `confidence` | 0 a 1, fracao ponderada dos fatores a favor |
| `reasons` | justificativas em texto |
| `invalidation` | o que derruba a leitura |

Alem do contrato: `factors` (cada fator avaliado, com favoravel/contrario/neutro),
`vies`, `niveis` (precos de **referencia**, nunca ordens) e `experimental`.

### Os quatro estados

| estado | quando |
|---|---|
| `NONE` | nada a acompanhar: dados insuficientes, volatilidade fora da faixa, medias embaralhadas |
| `WAIT` | existe vies, mas falta confirmacao - vale acompanhar |
| `BUY` / `SELL` | todas as condicoes obrigatorias atendidas e confianca acima do minimo |

## A baseline

Cinco condicoes obrigatorias, todas sobre o candle fechado:

1. **tendencia** - EMAs 9, 21 e 50 empilhadas na mesma ordem;
2. **inclinacao** - a EMA21 apontando para o lado do vies;
3. **gatilho** - preco fechando do lado certo da EMA9;
4. **volume** - volume do candle acima da media dos ultimos 20;
5. **ATR** - volatilidade dentro de uma faixa operavel (nem parado, nem explodindo).

Mais dois fatores que pesam na confianca sem serem obrigatorios: distancia do
preco a EMA21 (preco esticado) e o candle de confirmacao. Tudo em
`BaselineConfig`, sem numero magico solto.

## Tela Analise

`tela_analise(sinal)` mostra, nesta ordem: o aviso de que a estrategia e' de
validacao, o **sinal** com a confianca, as **justificativas**, os **fatores
favoraveis**, os **fatores contrarios**, os niveis de referencia e a
invalidacao.

A tela nunca esconde o que pesou contra: um BUY com dois fatores contrarios
listados e' informacao melhor do que um "COMPRAR" sozinho - e e' assim que da
para desconfiar da estrategia quando ela erra.

`linha_de_lista(sinal)` da uma linha por ativo, para varrer a watchlist.

## Escrevendo a proxima estrategia

Herde de `Strategy`, implemente `avaliar` e registre:

```python
class MinhaEstrategia(Strategy):
    nome = "minha-estrategia"

    def avaliar(self, contexto: StrategyContext) -> Signal:
        ...

registrar(MinhaEstrategia.nome, MinhaEstrategia)
```

Nada mais precisa mudar: o motor multi-timeframe continua entregando o
contexto sem lookahead, a tela Analise ja sabe desenhar o Signal e o Risk
Manager continua sendo quem decide tamanho - e quem pode dizer nao.
