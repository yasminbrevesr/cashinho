# Ticket Generator da Genial (`cashinho.core.genial`)

Traduz uma `Opportunity` aprovada em boletas prontas para **digitar** na
plataforma da Genial.

> ## Este modulo nao envia ordem
>
> Nesta etapa ele nao conhece API, token nem endpoint da Genial - e um teste
> percorre a arvore de sintaxe dos quatro arquivos garantindo que nenhum
> deles importa biblioteca de rede. O que sai daqui e' um roteiro de
> digitacao.

```python
from cashinho.core.genial import TicketGenerator, pagina

ticket = TicketGenerator().gerar(oportunidade, decisao_de_risco, preco_atual=31.02)
print(pagina(ticket))
```

Ou direto do Scanner, que ja tem a oportunidade e a decisao de risco:

```
python -m cashinho.core.scanner --boleta PETR4
python -m cashinho.core.scanner --boleta PETR4 --copiar   # so os campos
```

## O que e' nosso e o que e' da Genial

Esta e' a linha que o modulo inteiro respeita:

| nosso | da Genial |
|---|---|
| que tipo de boleta abrir (rompimento vira Stop, pullback vira limitada) | como a boleta se chama e se comporta |
| os precos, a quantidade e o offset em reais | o que o campo Offset significa |
| as condicoes de entrada e de cancelamento | quais validades existem e qual e' o padrao |

Tudo da coluna da direita sai marcado com **`REGRA GENIAL A CONFIRMAR`**, e a
tela termina listando cada pendencia com o que foi assumido e o que precisa
ser conferido. Nada disso foi verificado contra a documentacao deles.

Confirmou alguma? Abra `regras.py`, troque `status` para `CONFIRMADA` e
preencha `fonte`. O selo some sozinho da tela.

O campo mais ambiguo e' o **Offset**: em algumas plataformas e' a distancia
entre disparo e limite, em outras e' a distancia do stop movel. O Cashinho usa
o primeiro sentido e avisa.

## A escolha do tipo (isso e' logica de mercado)

| situacao | boleta |
|---|---|
| compra com entrada acima do preco atual | **Compra Stop** (rompimento) |
| compra com entrada abaixo ou igual | **Compra** (limitada, pullback) |
| venda com entrada abaixo do preco atual | **Venda Stop** |
| venda com entrada acima ou igual | **Venda** |
| protecao de uma compra | **Venda** (alvo) e **Venda Stop** (stop), ou uma OCO |
| protecao de uma venda | espelhado |

## A tela

Mostra os nove campos (Ativo, Quantidade, Validade, Preco, A Mercado, OCO,
Gain, Loss, Offset), os numeros da operacao (entrada, stop, alvo, risco
monetario, retorno potencial, R:R, score, setup, status, timestamp) e, sempre:

```
 ENTRAR SOMENTE SE:
   · o preco negociar acima de 31,15 (e' o que dispara a boleta)
   · o 60m continuar bullish quando voce for digitar
   · ainda estiver dentro da validade, ate 12:40

 CANCELAR A OPERACAO SE:
   · o preco fechar abaixo de 30,72 antes de a entrada disparar
   · passar de 12:40 sem a entrada ter disparado
```

As condicoes acompanham o tipo de boleta: uma Compra Stop fala em **romper**,
uma Compra limitada fala em **recuar**.

Os valores saem no formato de digitacao (`31,15`, sem `R$`), e
`bloco_para_copiar(ticket)` devolve so `campo: valor`, alinhados, sem
decoracao nem avisos - o bloco que se copia e digita.

## Sem aprovacao, sem boleta

Oportunidade em qualquer estado que nao seja `SETUP APROVADO` nao vira
boleta: o ticket volta com `gerado=False` e o motivo. O mesmo vale para
decisao recusada pelo Risk Manager.
