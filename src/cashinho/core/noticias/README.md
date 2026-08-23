# Noticias e eventos (`cashinho.core.noticias`)

Identifica **situacoes de risco** - divulgacao de resultados, fatos
relevantes, decisoes de juros, inflacao, payroll e eventos corporativos - e
entrega dado estruturado para o resto do pipeline.

```
python -m cashinho.core.noticias --modelo > eventos.json
python -m cashinho.core.noticias --arquivo eventos.json --ativo PETR4
python -m cashinho.core.noticias --arquivo eventos.json --json
```

```python
from cashinho.core.noticias import AvaliadorDeEventos, FonteArquivo
from cashinho.core.oportunidade import OpportunityEngine

motor = OpportunityEngine(eventos=AvaliadorDeEventos(FonteArquivo("eventos.json")))
```

## O dado estruturado

`Evento` carrega exatamente os campos pedidos - `event_type`, `symbol`,
`timestamp`, `severity`, `directional_bias`, `confidence`, `source` - mais
titulo, detalhe e `confirmado`.

`symbol` vazio significa **mercado inteiro**: juros, inflacao e payroll
atingem todos os ativos; resultados e fatos relevantes, so o ativo deles.

## Uma notícia nao gera compra nem venda

Isto nao e' recomendacao no README, e' o formato dos objetos:

- `AvaliacaoDeEventos` **nao tem campo de direcao**. Nao ha o que preencher
  com "compre" - o objeto recusa no construtor `ajuste_de_score` positivo e
  `multiplicador_de_risco` abaixo de 1;
- `Evento.contraria(direcao)` existe; o espelho dele, um `confirma()`, **nao
  existe**. Este modulo so sabe apontar risco;
- `directional_bias` entra so como **agravante**: notícia contra a operacao
  desconta mais. Notícia a favor nao desconta menos - senao a manchete boa
  estaria, na pratica, empurrando a operacao;
- um teste varre os arquivos do modulo procurando `Action.BUY`, `Action.SELL`,
  `Direction.LONG/SHORT`, `Signal(`, `Opportunity(` e `place_order`.

## Os tres efeitos

| efeito | como | limite |
|---|---|---|
| **reduzir score** | penalidade por severidade, somada e limitada | teto de 40 pontos |
| **aumentar risco** | `risco_ajustado()` divide o risco por trade | ate 2x menos posicao |
| **bloquear** | janela por tipo de evento | so severidade >= ALTA, e so confirmado |

As janelas de bloqueio (configuraveis):

| evento | antes | depois |
|---|---|---|
| resultados | 60 min | 60 min |
| decisao de juros | 30 min | 45 min |
| inflacao | 15 min | 30 min |
| payroll | 15 min | 30 min |
| fato relevante | **0** | 120 min |
| evento corporativo | 0 | 0 (so desconta) |

O zero do fato relevante nao e' descuido: **fato relevante nao e' agendado**.
Ele aparece. Deixar um fato relevante futuro pesar antes da hora seria ler o
jornal de amanha - o mesmo look-ahead que o resto do robo passa o tempo
evitando. O modulo ignora qualquer evento nao agendavel com data no futuro.

## No Opportunity Engine

O motor recebe o avaliador e aplica a agenda **antes** de decidir o estado -
o desconto precisa valer na mesma conta que aprova ou rejeita:

```
score dos componentes    39
Noticias e eventos      -25
  └ JUROS MERCADO
SCORE FINAL              14
```

O desconto aparece como **linha**, nunca como numero que mudou sozinho: a
regra da tela de score continua valendo, e `total_bruto` guarda o valor de
antes. Bloqueio so rebaixa o estado para `NAO OPERAR`; nao existe evento que
promova uma oportunidade.

## Fontes: nao inventar notícia

A fonte suportada nesta versao e' o **arquivo de calendario** que voce mantem
ou exporta da corretora (`--modelo` gera o esqueleto). Um registro so vira
evento se trouxer tipo, data, severidade e **origem**; o que faltar e'
descartado com o motivo guardado e mostrado na tela - nunca completado com um
palpite razoavel. Tipo desconhecido nao e' encaixado no mais parecido.

**FONTE DE NOTICIAS EM TEMPO REAL A CONFIRMAR.** Nao ha feed integrado: os
provedores confiaveis sao pagos e os gratuitos nao tem compromisso de
atualizacao. Uma agenda que atrasa e' pior que agenda nenhuma, porque parece
que existe.

## NOTICIAS INDISPONIVEIS

O arquivo precisa de `atualizado_em`. Sem isso - ou com idade acima da
validade (12h por padrao) - a agenda vira `NOTICIAS INDISPONIVEIS`, e a
politica **ignora todos os eventos dela** para decidir. A tela continua
mostrando os eventos, marcados, porque esconder seria pior.

Tres estados que nao podem ser confundidos:

- agenda **disponivel e vazia**: nao ha evento a vista;
- agenda **desatualizada**: existe, mas nao vale;
- **sem fonte**: ninguem configurou nada.

Por padrao, agenda indisponivel **avisa e nao bloqueia** - bloquear tudo por
falta de um arquivo opcional deixaria o robo inutil. Quem preferir o
contrario liga `ConfigEventos(sem_fonte_bloqueia=True)`, e ai nenhuma
operacao passa sem agenda fresca.

## O que este modulo nao faz

- **nao le manchete e nao interpreta texto.** Ele le uma agenda estruturada;
- **nao inventa evento**, nem completa registro pela metade;
- **nao aprova nada.** O maximo que consegue e' descontar, reduzir posicao e
  bloquear.
