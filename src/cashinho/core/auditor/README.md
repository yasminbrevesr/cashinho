# Contrarian Auditor (`cashinho.core.auditor`)

O advogado do diabo do sistema. Enquanto a estrategia e o score procuram
razoes para operar, o auditor procura razoes para **nao** operar - e uma
rejeicao critica dele impede a aprovacao, por mais alto que esteja o score.

```python
from cashinho.core.auditor import ContrarianAuditor

auditoria = ContrarianAuditor().auditar(oportunidade, vista)

auditoria.approved              # False se houver rejeicao critica
auditoria.warnings              # alertas (descontam score, nao bloqueiam)
auditoria.critical_rejections   # o que barrou
auditoria.score_adjustment      # quanto foi descontado
auditoria.reasons               # as frases, criticas primeiro
```

## As onze frentes de invalidacao

| frente | critico quando | alerta quando |
|---|---|---|
| resistencia proxima | parede a menos de 0,7 ATR da entrada (compra) | ate 1,5 ATR |
| suporte proximo | chao a menos de 0,7 ATR (venda) | ate 1,5 ATR |
| baixo volume | abaixo de 0,7x a media | abaixo de 1,0x |
| divergencias | — | preco fez novo extremo e o RSI nao acompanhou |
| entrada atrasada | preco a 3,5+ ATR da EMA21 | a partir de 2,0 ATR |
| risco/retorno ruim | RR abaixo de 1,2 | abaixo de 1,8 |
| volatilidade excessiva | ATR acima de 3% do preco | acima de 2% |
| falso rompimento | a operacao vai no sentido do rompimento que falhou | — |
| timeframes conflitantes | duas ou mais camadas contra | uma camada contra, ou duas neutras |
| stop muito distante | 3,5+ ATR ou 3%+ do preco | a partir de 2,5 ATR |
| oportunidade expirada | `expires_at` ficou para tras | — |

Todos os limiares estao em `ConfigAuditor` - de proposito mais duros que os do
score, senao o auditor vira carimbo.

## Tres respostas possiveis, nao duas

Cada frente devolve **favoravel**, **contraria** ou **nao verificada**:

- *favoravel* - o auditor tentou invalidar e nao conseguiu, com o numero que
  sustenta a afirmacao ("3,2 ATR de espaco livre ate a resistencia");
- *contraria* - achou algo (alerta ou critico), com a evidencia;
- *nao verificada* - faltou dado. **Nao vira fator favoravel**: ausencia de
  evidencia nao e' evidencia de ausencia.

## O fluxo obrigatorio

```
Strategy -> Opportunity -> Score -> Auditor -> Risk Manager -> Resultado
```

`Pipeline` implementa isso literalmente. Cada etapa registra se passou e por
que; quando uma barra, as seguintes ficam marcadas como nao executadas e o
resultado diz onde parou. Um teste percorre todas as execucoes e verifica que
**o Risk Manager nunca e' consultado sem o auditor ter aprovado antes** - nao
existe atalho no codigo.

```python
from cashinho.core.auditor import Pipeline

resultado = Pipeline(estrategia, engine, auditor, risco).executar(vista, "PETR4")
resultado.aprovado      # so True se as cinco etapas passaram
resultado.parou_em      # a etapa que barrou
```

O auditor tambem se recusa a aprovar o que o engine nao aprovou: uma
oportunidade que chega como `AGUARDANDO GATILHO` sai reprovada, com esse
motivo.

## Na tela

```
 AUDITOR
   tentei invalidar esta oportunidade em 11 frentes

   FATORES FAVORAVEIS  (nao consegui invalidar)
     ✔ volatilidade excessiva: ATR de 0.50% do preco, dentro do operavel
   FATORES CONTRARIOS
     ! timeframes conflitantes: camada(s) apontando para o outro lado: 60m bearish  (-6 pts)
   RISCOS ENCONTRADOS  (rejeicao critica)
     ✖ risco/retorno ruim: risco/retorno de 0.38: o alvo nao paga o risco
     ✖ oportunidade expirada: a janela terminou as 12:33 (4 min atras)
   DECISAO
     REPROVADO PELO AUDITOR
     3 rejeicao(oes) critica(s): risco/retorno ruim; stop muito distante; oportunidade expirada
     score 88 -> 7  (ajuste -81)
```

A secao aparece sozinha na tela Analise quando o sinal traz uma auditoria em
`Signal.extras["auditoria"]`, e `pagina_resultado()` mostra o fluxo inteiro,
das cinco etapas ao dimensionamento do risco.
