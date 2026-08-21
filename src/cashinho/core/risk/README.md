# Risk Manager (`cashinho.core.risk`)

O guarda-costas do capital. **Independente de estrategia por construcao**: a
unica entrada e' ativo, direcao, entrada e stop. Nao ha campo para setup,
score, indicador ou "confianca" - nada com que uma estrategia possa negociar.

```python
from cashinho.core.risk import PedidoOperacao, RiskConfig, RiskManager
from cashinho.models import Direction

rm = RiskManager(RiskConfig(capital=50_000, risco_por_trade_pct=1.0))
decisao = rm.avaliar(PedidoOperacao("PETR4", Direction.LONG, entrada=31.00, stop=30.70))

decisao.allowed              # True/False
decisao.reason               # por que passou ou por que nao passou
decisao.position_size        # quantidade recomendada
decisao.monetary_risk        # risco real em R$ (quantidade x risco por acao)
decisao.portfolio_exposure   # exposicao da carteira ja com esta ordem

if decisao.allowed:
    rm.abrir(decisao)        # so aceita decisao aprovada emitida por este gerente
```

## Limites suportados

| limite | campo |
|---|---|
| capital disponivel | `capital` |
| risco percentual por operacao | `risco_por_trade_pct` |
| risco monetario maximo | `risco_max_monetario` |
| exposicao maxima por ativo | `exposicao_max_por_ativo_pct` |
| exposicao total maxima | `exposicao_max_total_pct` |
| perda maxima diaria | `perda_max_diaria_pct` / `perda_max_diaria_valor` |
| numero maximo de trades por dia | `max_trades_dia` |
| perdas consecutivas maximas | `max_perdas_consecutivas` |
| drawdown maximo | `drawdown_max_pct` |
| kill switch | `rm.acionar_kill_switch()` / `rm.liberar_kill_switch()` |

## O calculo

```
risco monetario = capital x percentual de risco
risco por acao  = abs(entrada - stop)
quantidade      = floor(risco monetario / risco por acao)
```

e, em seguida, o corte pelo que existe de fato:

1. **caixa disponivel** (patrimonio - exposicao ja aberta);
2. **exposicao maxima por ativo** (descontando a posicao que ja existe nele);
3. **exposicao maxima total**;
4. **lote padrao**, quando o fracionario esta desligado.

Todo arredondamento e' para baixo - na duvida, arrisca menos. O `limitador`
da decisao diz qual restricao definiu o tamanho.

Duas regras que valem a pena conhecer:

- o risco de uma operacao **nunca passa do que resta da perda diaria**: com
  perda diaria de 3% e risco por trade de 5%, o trade sai com 3%; depois de
  perder 2,5%, o proximo sai com 0,5%;
- a perda maxima diaria e' medida sobre o **capital da abertura do pregao**,
  nao sobre o patrimonio que encolhe durante o dia - senao o limite fugiria
  junto com o prejuizo.

## Nenhuma estrategia sobrescreve uma rejeicao

Tres camadas, todas cobertas por teste:

1. `RiskDecision` e' congelada - `decisao.allowed = True` levanta
   `FrozenInstanceError`;
2. `rm.abrir()` so aceita uma decisao **emitida por este gerente, aprovada e
   ainda nao usada** (id de uso unico): decisao forjada na mao, copiada com
   `dataclasses.replace(allowed=True)`, reaproveitada ou vinda de outro
   gerente e' recusada com `RiskRejectionError`;
3. os bloqueios sao **reavaliados na hora de abrir**: se o kill switch foi
   acionado ou um limite estourou entre a analise e a execucao, a ordem nao
   passa.

Trocar limites (`atualizar_config`) tambem invalida as decisoes ja emitidas.

## Kill switch

Arma sozinho quando um limite duro e' atingido e diz como desarma:

| gatilho | desarma |
|---|---|
| perda maxima diaria | no proximo pregao (`novo_pregao`) |
| perdas consecutivas | no proximo pregao |
| drawdown maximo | so manualmente |
| manual | so manualmente |

## Pagina Risk Manager

```
python -m cashinho.core.risk                                   # a pagina
python -m cashinho.core.risk configurar --capital 40000 --risco-trade 0.5 \
        --perda-diaria 2 --max-trades 3 --exposicao-max 50
python -m cashinho.core.risk simular PETR4 compra 31.00 30.70
python -m cashinho.core.risk kill-switch on --motivo "mercado maluco"
python -m cashinho.core.risk novo-pregao
```

A primeira coisa da pagina e' a faixa de status - **TRADING LIBERADO** ou
**TRADING BLOQUEADO**, com o motivo do bloqueio logo abaixo -, seguida do uso
de cada limite, da configuracao e das posicoes abertas. Configuracao e estado
ficam em `~/.cashinho` (mude com `--dados`). O comando sai com codigo 1
quando o trading esta bloqueado, o que permite usar em script.

Para uma interface grafica, `status.para_dict()` e `decisao.para_dict()`
entregam o mesmo conteudo em JSON.
