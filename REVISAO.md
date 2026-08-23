# Revisao tecnica do MVP - Cashinho

Revisao completa das 20 areas pedidas, com a suite inteira executada antes e
depois. **Nenhuma funcionalidade nova foi implementada.**

- suite antes: **1479 testes** (1 skip), 84s
- suite depois: **1507 testes** (1 skip), 85s - as 28 diferencas sao testes de
  regressao das correcoes abaixo
- codigo: 24.222 linhas em 147 arquivos; testes: 16.743 linhas em 124 arquivos

---

## Correcoes aplicadas (criticos e crashes)

### 1. CRITICO - o `Candle` aceitava estado impossivel

`Candle` e' o atomo do sistema: ATR, estrutura, stop, tamanho de posicao e
preco de ordem saem dele. Ele nao tinha **nenhuma** validacao, e aceitava
calado:

| entrada | antes | agora |
|---|---|---|
| maxima abaixo da minima | aceito | `CandleInvalidoError` |
| fechamento fora do range | aceito | `CandleInvalidoError` |
| preco zero ou negativo | aceito | `CandleInvalidoError` |
| volume negativo | aceito | `CandleInvalidoError` |
| NaN / infinito | aceito | `CandleInvalidoError` |

Uma linha corrompida do feed virava ATR errado, stop errado e tamanho de
posicao errado, sem nenhum sinal. `CandleInvalidoError` herda de `ValueError`
justamente porque os provedores ja capturam `ValueError` por linha: **a linha
ruim e' descartada, a serie continua**. Ha tolerancia de 1e-9 para ruido de
ponto flutuante (um close 1e-12 acima da maxima veio de aritmetica, nao do
mercado), e candle achatado (`high == low`) continua valido.

A suite inteira passou sem alteracao apos a trava: nada no sistema construia
candle impossivel - era guarda faltando, nao comportamento em uso.

### 2. O provedor Yahoo quebrava a busca inteira por causa de uma linha

A construcao do `Candle` estava **fora** do `try` que trata a linha. Com a
validacao nova, uma unica linha incoerente derrubaria o download completo.
Movida para dentro: linha ruim cai fora, o resto da serie vive. Mesmo ajuste
na fonte de juros do Banco Central (`FonteBCB`).

### 3. Ordem OCO unica perdia a perna de gain em silencio

`OrderType.OCO` existe no enum, mas uma ordem unica desse tipo caia no ramo de
stop do `_gatilho` e o `preco_limite` era **ignorado sem aviso**: o operador
achava que tinha ordem de gain, e nao tinha. Nenhum caminho do sistema fazia
isso hoje (todo OCO real passa por `place_oco`), entao era armadilha latente.
Agora e' recusada com o caminho certo na mensagem.

### 4. `perfil_volume` estourava com divisao por zero

Um candle parado na maxima da serie caia um balde alem do fim (`i0` nao era
limitado ao ultimo bin como `i1`), zerando o divisor. Funcao publica, sem
consumidor hoje - crash real com dado real.

---

## Problemas importantes (nao corrigidos - por escolha)

| # | area | problema | onde |
|---|---|---|---|
| 1 | logs | **nao existe log nenhum** (0 usos de `logging`). Divergencia entre risco e corretora vira string em `BrokerComRisco.avisos`, que ninguem le | todo o projeto |
| 2 | duplicacao | helper de cores `_c()`/`_CORES` copiado em **18** arquivos de view; `LARGURA` em 15; `_data()` em 6 CLIs; `_num()` em 4; `barra()` em 2 | `core/*/view.py` |
| 3 | testes | camada `indicators/` (980 linhas) tinha **zero testes diretos** ate esta revisao - e era exatamente onde estava o crash #4. ~20 funcoes publicas sem nenhum consumidor | `indicators/` |
| 4 | erros | 19 excecoes proprias **sem base comum**: nao da para escrever `except CashinhoError`. Pior: **tres classes diferentes chamadas `ConfiguracaoInvalidaError`** (mtf, risk, scanner), com hierarquias incompativeis | vario |
| 5 | arquitetura | `data/synthetic.py` (camada 1) importa `core/mtf/session` (camada 2). A sessao da B3 e' primitiva de dominio e esta em `core` | `data/synthetic.py:16` |
| 6 | arquitetura | `strategy/view.py` importa views de `oportunidade` e `auditor` (camadas acima). Sao imports locais, entao nao ha ciclo em tempo de carga - mas a dependencia existe | `strategy/view.py:154,164` |
| 7 | banco | `DiarioDeTrades.carregar` descarta linha corrompida **em silencio**. O modulo de noticias ja faz o certo (guarda `descartados` e mostra na tela); o diario, nao | `diario/diario.py:99` |
| 8 | banco | gravacao de estado (paper broker, risco, config) usa `write_text` direto: processo morto no meio deixa arquivo truncado. O diario em JSONL (append-only) esta certo; o resto, nao | `broker/__main__.py:91` |
| 9 | performance | caches de estrutura e confluencia **sem limite**: ~50 KB retidos por avaliacao. Medido: 200 avaliacoes = 10 MB, 47 ms cada. Um scanner de 20 ativos sobre um pregao inteiro passa de 400 MB | `oportunidade/engine.py:89` |
| 10 | interface | `pagina_oportunidade` - a tela mais rica do sistema (score aberto, CONTEXTO DO MERCADO, NOTICIAS E EVENTOS) - **nao e' impressa por nenhuma CLI** | `oportunidade/view.py` |
| 11 | interface | a CLI de risco e' a unica das 10 sem `--json` | `risk/__main__.py` |
| 12 | qualidade | `volume_relativo` inclui o proprio candle na media: um pico de 3x le 2,7x. E' convencao valida, mas nao estava escrita em lugar nenhum e o limiar do score depende dela | `indicators/volume.py:85` |

O item 12 **nao foi alterado de proposito**: mexer nele mudaria o componente
de volume do score e, por tabela, o comportamento das estrategias. Ficou
registrado em teste (`tests/indicators/test_volume.py`).

---

## Melhorias futuras

1. **Log estruturado** (JSONL, como o diario) com nivel por componente,
   alimentando a `Telemetria` do System Health - hoje a telemetria so tem o
   que alguem lembrou de anotar, e some quando o processo morre.
2. **Extrair `core/ui/`** com cores, largura, barra, formatadores e parsers de
   data. Elimina as 18 copias e da consistencia de tela de graca.
3. **`CashinhoError` como base** das 19 excecoes, e renomear os tres
   `ConfiguracaoInvalidaError` homonimos.
4. **Mover a sessao da B3** para `cashinho/sessao.py`, abaixo de `data` e
   `core`.
5. **Limite nos caches** (LRU por tamanho) e `limpar()` entre ativos no
   scanner.
6. **CLI de analise** (`python -m cashinho.core.oportunidade --ativo PETR4`)
   imprimindo a tela completa.
7. **Escrita atomica** de estado (arquivo temporario + `os.replace`).
8. **Cobertura medida**: `pytest-cov` nao esta instalado e nao ha rede neste
   ambiente. A cobertura reportada abaixo e' funcional, nao de linha.

---

## As 20 areas

| # | area | veredito |
|---|---|---|
| 1 | arquitetura | boa: modulos coesos, sem ciclo em tempo de carga. 2 inversoes de camada reais (itens 5 e 6) |
| 2 | duplicacao | **o ponto mais fraco**: 18 copias do helper de cores (item 2) |
| 3 | bugs | 4 encontrados e corrigidos; nenhum critico remanescente conhecido |
| 4 | tratamento de erros | consistente por modulo (falha vira estado descrito, nao excecao solta), mas sem base comum (item 4) |
| 5 | qualidade dos dados | era o **buraco critico** (candle sem validacao) - corrigido. Contexto e noticias ja tratavam ausencia com rigor |
| 6 | Risk Manager | solido: decisao de uso unico, reuso barrado, exposicao volta ao fechar, stop invertido recusado, quantidade nunca excede capital |
| 7 | look-ahead | **a area mais bem defendida**. Backtest, fita de replay e vista multi-timeframe verificados de forma adversarial: nenhum vazamento |
| 8 | backtesting | correto: entrada no candle seguinte, custos sempre contra, saida pessimista, fechamento forcado no fim da sessao |
| 9 | multi-timeframe | correto: barra so aparece depois de fechada; cache com `symbol` na chave |
| 10 | Paper Broker | conservacao de dinheiro confere; saldo, short, kill switch e round-trip de serializacao ok. 1 armadilha corrigida (item 3 das correcoes) |
| 11 | scanner | isola ativo quebrado sem derrubar a varredura; contaminacao entre ativos ja corrigida antes |
| 12 | score | pesos normalizados, pisos por componente, penalidades visiveis com `total_bruto` preservado |
| 13 | auditor | rejeicao critica realmente impede aprovacao |
| 14 | boleta | fiel a oportunidade (entrada/stop/alvo conferidos), nao gera boleta sem aprovacao, zero import de rede, 8 regras marcadas A CONFIRMAR |
| 15 | banco | JSONL append-only e' a escolha certa; 2 ressalvas (itens 7 e 8) |
| 16 | interface | 10 CLIs, todas com `--json` menos uma; a tela mais rica sem CLI (itens 10 e 11) |
| 17 | logs | **ausentes** (item 1) |
| 18 | testes | 1507 testes, distribuidos; `indicators/` era o vazio (item 3), agora com testes |
| 19 | seguranca | limpa: zero `eval`/`exec`/`pickle`/`subprocess`, zero credencial, zero chamada de rede fora de `data/` e do contexto |
| 20 | performance | 47 ms por avaliacao; caches sem limite (item 9) |
