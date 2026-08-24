# Pecas de tela (`cashinho.core.ui`)

O modulo que existe para os outros nao precisarem repetir.

```python
from ..ui import c, num, pct, barra
from ..ui.argumentos import data, percentuais
```

## Por que ele existe

A revisao tecnica contou: o mesmo dicionario de cores e a mesma funcao `_c`
estavam copiados em **18** arquivos de view, `LARGURA` em 15, o parser `_data()`
em 6 CLIs, `_num()` em 4.

Copia nao e' so feio. Quando o replay ganhou azul e o risco ganhou inverso, as
outras dezesseis telas nao ganharam - e a diferenca so aparecia na tela. Quando
uma CLI melhorava a mensagem de "data invalida", as outras cinco continuavam
com a antiga.

A extracao removeu **268 linhas** sem mudar uma unica saida: a suite inteira
passou sem alteracao de teste.

## O que fica aqui - e o que nao fica

Fica: **como** pintar, formatar e converter argumento.

Nao fica: **quando**. Que numero e' verde, quando uma barra enche, qual a
largura da tela - isso e' de cada tela, e continua la. Por isso `LARGURA` nao
foi centralizado: ele vale de 64 a 108 conforme a tela, e um valor unico seria
uma decisao de layout tomada no lugar errado.

## Cores

`c(texto, *estilos, ativo=False)` devolve o texto limpo - e' assim que
`--sem-cor` e a saida para arquivo funcionam sem um `if` em cada tela. Estilo
desconhecido e' ignorado em vez de levantar: uma cor errada nao pode derrubar
um painel de risco.

A paleta tem apelidos semanticos (`alta`, `baixa`, `neutro`, `fraco`) apontando
para as mesmas cores. A tela de estrutura fala nesses termos, e o apelido e'
traducao - nao uma segunda paleta que pode divergir.

## Formato

`pct()` tem uma regra que veio de um bug real: **`-0,00%` vira `0,00%`**. Um
sinal negativo em zero mente sobre a direcao do movimento.

`num()` e `hora()` devolvem `-` quando o valor e' `None`. Nunca zero: zero e'
uma afirmacao sobre o mercado, e ausencia de dado nao e' uma afirmacao.

## Argumentos de CLI

`percentuais()` aceita `0.6,0.2,0.2` e `60,20,20` - e recusa o resto. Reescalar
qualquer soma seria conveniente e silencioso: `0.5,0.3,0.3` viraria 45/27/27 sem
ninguem avisar, e a divisao pedida nao seria a divisao feita.

## A duplicacao nao volta

Dois testes em `tests/core/ui/` falham se alguem recriar um `_CORES = {` fora
daqui ou um `def _data(` numa CLI.
