# Market Context (`cashinho.core.contexto`)

Descreve **o ambiente de mercado** - Ibovespa, dolar, juros, petroleo, minerio
e indices internacionais - e diz o quanto disso ele realmente sabe.

```
python -m cashinho.core.contexto
python -m cashinho.core.contexto --fonte real
python -m cashinho.core.contexto --instrumentos ibovespa,dolar,sp500 --json
python -m cashinho.core.contexto --listar-instrumentos
```

```python
from cashinho.core.contexto import MotorDeContexto, fonte_yahoo, FonteBCB, FonteComposta

contexto = MotorDeContexto(FonteComposta([fonte_yahoo(), FonteBCB()])).montar()
contexto.market_regime        # RegimeDeMercado.RISCO_LIGADO
contexto.data_quality.nivel   # NivelDeQualidade.BOA
```

## O objeto

`MarketContext` carrega exatamente os campos pedidos - `timestamp`,
`market_regime`, `ibovespa_direction`, `volatility`, `relevant_correlations`,
`data_quality` - mais a leitura instrumento a instrumento, para a tela.

Ele **nao tem entrada, stop nem alvo**, e nao ha metodo aqui que produza
qualquer um dos tres.

## Fontes: so o que da para usar

Cada instrumento existe no catalogo **com a fonte declarada por nome**. Nada e'
buscado por adivinhacao de ticker.

| instrumento | fonte | observacao |
|---|---|---|
| Ibovespa | Yahoo `^BVSP` | intradiario com atraso (~15 min) |
| Dolar (USD/BRL) | Yahoo `USDBRL=X` | |
| Juros (CDI) | Banco Central, SGS serie 12 | API oficial, **diaria** |
| Petroleo (Brent) | Yahoo `BZ=F` | futuro continuo: a rolagem vira salto |
| S&P 500 / Nasdaq | Yahoo `^GSPC` / `^IXIC` | |
| **Minerio de ferro** | **nenhuma** | `FONTE A CONFIRMAR` |

Minerio ficou sem fonte de proposito. O preco de referencia (Platts/SGX) e'
pago e nao tem fonte publica confiavel, e deriva-lo de VALE3 seria inventar
uma cotacao com cara de dado. Ele continua no catalogo, aparece na tela, e
nunca recebe numero.

Quando uma fonte falha, o instrumento entra como **indisponivel com o motivo**
- nunca com o ultimo valor conhecido, nunca com zero.

## Qualidade dos dados nao e' enfeite

`data_quality` diz quantas fontes responderam, quais faltaram, quais nao tem
fonte, e qual o atraso do dado mais velho. E' o **unico portao** entre o
contexto e qualquer decisao: `NivelDeQualidade.confiavel` e' falso para
`RUIM`, `INDISPONIVEL` e `SIMULADA`.

Medir e confiar sao coisas diferentes, e o modulo separa as duas: uma leitura
simulada e' *mensuravel* (a tela de demonstracao mostra regime, direcao e
volatilidade) e nao e' *confiavel* (o fator nao pesa nada com ela). Sem essa
separacao, a demonstracao ou nao mostrava nada, ou mentia.

## O regime

As regras cabem em uma tela e sao explicitas de proposito - da para ler e
discordar:

- volatilidade **extrema** contra o proprio historico do indice, ou queda com
  volatilidade alta -> `ESTRESSE`;
- Ibovespa em alta com dolar comportado -> `RISCO_LIGADO`;
- Ibovespa em baixa com dolar em alta -> `RISCO_DESLIGADO`;
- indice de lado -> `LATERAL`;
- bolsa e dolar no **mesmo** sentido -> `CONFLITANTE` (no Brasil eles costumam
  andar opostos; quando nao andam, a leitura de ambiente perde forca);
- sem Ibovespa utilizavel -> `INDEFINIDO`. Faltar dado nao e' "mercado de
  lado".

## Correlacoes com amostra junto

Duas armadilhas evitadas no codigo, nao no comentario:

1. **alinhamento por timestamp.** Ibovespa e S&P 500 tem feriados diferentes;
   casar o i-esimo candle de um com o i-esimo do outro compara dias distintos
   e produz um numero bonito e falso;
2. **amostra minima.** Com cinco pontos qualquer par parece correlacionado.
   Abaixo de 30 observacoes a correlacao nao e' calculada, e toda correlacao
   exibida mostra o tamanho da amostra ao lado.

## Como uma estrategia usa - e o que ela nao consegue fazer

```python
from cashinho.core.contexto import aplicar_contexto, EstrategiaComContexto

sinal = aplicar_contexto(sinal, contexto)            # anexa o fator
estrategia = EstrategiaComContexto(minha_estrategia, contexto)  # ou embrulha
```

O enunciado desta camada e' que o contexto **pode pesar mas nao pode gerar
operacao sozinho**. Isso nao e' recomendacao no README, e' o formato da
funcao:

- `aplicar_contexto` recebe um `Signal` **que ja existe** e devolve outro com
  a **mesma `action`**. Nao ha caminho de codigo que troque WAIT por BUY - e
  ha teste parametrizado cobrindo todas as combinacoes de acao e regime;
- um sinal que nao e' acionavel **nao ganha confianca nenhuma**. Um WAIT com
  confianca inflada seria uma operacao entrando pela porta dos fundos, mais
  adiante no pipeline;
- o ajuste e' limitado a `LIMITE_DE_AJUSTE` (0,08). Contexto bom nao
  transforma leitura fraca em leitura forte;
- contexto com qualidade insuficiente entra como fator **neutro**, com o
  motivo na tela.

## A tela

`secao_contexto(contexto)` devolve a secao CONTEXTO DO MERCADO pronta para
embutir em qualquer tela - a de oportunidade ja aceita
(`pagina_oportunidade(op, contexto=...)`).

```
 CONTEXTO DO MERCADO                                        21/08 12:30
  REGIME          RISCO LIGADO
  IBOVESPA        ALTA
  VOLATILIDADE    NORMAL
  QUALIDADE       PARCIAL  4 de 6 fontes · atraso 15 min · 1 sem fonte confirmada

  INSTRUMENTO                   ULTIMO      DIA   ESTADO
  Ibovespa                     134.210   +0,84%   ok
  Dolar (USD/BRL)               5,4210   -0,31%   ok
  Minerio de ferro                   -        -   FONTE A CONFIRMAR
```

Nenhuma linha e' escondida: um instrumento que nao veio aparece dizendo por
que. Omitir a linha faria o contexto parecer mais completo do que e'.

## O que este modulo nao faz

- **nao inventa cotacao.** Sem fonte confiavel, o campo fica vazio e marcado;
- **nao aponta ativo nem operacao.** Ele descreve ambiente;
- **nao decide sozinho.** O maximo que consegue e' mover 0,08 de confianca de
  um sinal que outra camada ja produziu.
