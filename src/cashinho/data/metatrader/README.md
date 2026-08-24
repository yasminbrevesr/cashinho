# MetaTrader 5 / Genial (`cashinho.data.metatrader`)

Market Data **em tempo real** da B3, pelo terminal da Genial.

```
B3 → Genial → MetaTrader 5 → MetaTraderMarketDataProvider → domínio do Cashinho
```

**Somente leitura.** A capacidade `trading` é `False`, não existe método de
envio de ordem nesta camada, e há teste que varre a árvore sintática dos
arquivos procurando `order_send`, `place_order` e afins.

## Como ligar (na máquina Windows)

1. instale o **MetaTrader 5 da Genial**;
2. abra e **autentique manualmente** (o Cashinho nunca guarda sua senha,
   assinatura eletrônica ou número de conta);
3. abra a **Observação do Mercado** com `Ctrl+M`;
4. abra a **seleção de ativos** com `Ctrl+U`;
5. adicione **PETR4**;
6. **deixe o terminal aberto** — o Cashinho conecta no terminal já autenticado;
7. ative o `.venv` do projeto;
8. `pip install MetaTrader5` (só existe no Windows);
9. `python scripts/check_mt5.py` — o diagnóstico oficial;
10. `python -m cashinho.data --ativo PETR4 --provider metatrader --cotacao`.

No `.env`:

```
MARKET_DATA_REALTIME_PROVIDER=metatrader
MT5_TERMINAL_PATH=                       # vazio = o MT5 se acha sozinho
MT5_SERVER_TIMEZONE=America/Sao_Paulo
MT5_STALE_SECONDS=60
MT5_REFRESH_SECONDS=5
```

## O fuso: o erro de 3 horas

O timestamp que o MT5 devolve **não é UTC** — é o relógio do servidor da
corretora empacotado como epoch. Converter com
`datetime.fromtimestamp(bruto, tz=UTC).astimezone(BRT)` joga tudo 3 horas para
trás: um negócio das **17:05** vira **14:05**, e o robô passa a acreditar num
pregão que não existiu.

`NormalizadorDeTempoDoBroker` faz o caminho certo, em três passos:

```
número bruto do MT5
  → relógio de parede que ele representa   (sem fuso)
  → esse relógio COM o fuso do servidor    (MT5_SERVER_TIMEZONE)
  → convertido para o fuso do domínio
```

O segundo passo é o que costuma faltar. Há teste que reproduz o erro e prova
a diferença de exatamente 3 horas.

## Quote e Trade são fontes separadas

`symbol_info_tick()` **não serve** como retrato do mercado: na máquina real ele
voltou com `bid=0.0`, `ask=0.0` e `last=42.11` **existindo** histórico de
bid/ask válido. Por isso:

| o quê | de onde vem |
|---|---|
| `bid`, `ask`, `quote_timestamp` | `COPY_TICKS_INFO` |
| `last`, `volume`, `trade_timestamp` | `COPY_TICKS_TRADE` |

Os dois relógios ficam **separados** no snapshot — juntá-los num campo só
esconderia qual dos dois está velho.

## Bid/Ask zerados não são preço

No fim do pregão o terminal devolve `bid=0` e `ask=0`. Isso é **ausência de
livro**, não preço zero:

```
bid = None
ask = None
spread = None
status = NO_ACTIVE_BOOK
```

O último negócio continua disponível, **à parte e com a idade dele**.
Preencher o bid com o last seria inventar cotação.

## Símbolos: exata primeiro

A Genial expõe `PETR4`, `PETR4F`, `PETR4T`, `PETR4M`, `PETR4Q`, `PETR4R`.
Buscar por `"PETR4" in nome` casa com os seis. A resolução é:

1. **correspondência exata** — o único caminho automático;
2. sem exata → `SYMBOL_AMBIGUOUS` nomeando os candidatos, ou
   `SYMBOL_NOT_FOUND`.

Nunca uma escolha silenciosa: analisar o fracionário achando que é a ação é
erro caro.

## Candle em formação

A posição 0 do MT5 é o candle **abrindo agora**. O corte não é `rates[:-1]` —
isso jogaria fora um candle fechado sempre que a consulta caísse logo depois
da virada do período. A regra é temporal: *o candle só está fechado quando o
período dele já terminou*, e é testada nos dois sentidos.

## Estados do feed

`initialize() == True` **não basta** para dizer ONLINE. O estado considera
terminal conectado, símbolo resolvido, idade do dado e se há livro:

| situação | estado |
|---|---|
| tick recente, livro cheio | `ONLINE` |
| bid/ask zerados | `NO_ACTIVE_BOOK` |
| parado, **dentro** do pregão | `STALE` |
| parado, **fora** do pregão | `MARKET_CLOSED` |
| terminal caído / sem tick | `OFFLINE` |

**Limite conhecido:** a distinção mercado-aberto/fechado usa a sessão regular
da B3 e **não conhece feriados**. Num feriado, dado parado aparece como
`STALE` em vez de `MARKET_CLOSED` — conservador na direção certa (avisa
demais, nunca de menos).

## Sem fallback

Se o terminal cair, o serviço **recusa** a finalidade de tempo real em vez de
servir dado histórico como se fosse mercado. Research e backtest continuam
usando os provedores históricos, separadamente.

## Segurança

Nada da conta sai daqui: o adapter lê `account_info()` apenas para o **nome do
servidor**, e `para_dict()` não carrega login, saldo nem patrimônio — há teste
para isso.
