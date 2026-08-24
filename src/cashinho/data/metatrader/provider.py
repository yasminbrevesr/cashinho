"""``MetaTraderMarketDataProvider``: Market Data em tempo real via Genial/MT5.

    B3 -> Genial -> MetaTrader 5 -> este adapter -> dominio do Cashinho

**Somente leitura.** A capacidade ``trading`` e' falsa e nao ha metodo de
envio de ordem nesta classe - ha teste que varre o arquivo procurando por
``order_send``, ``buy``, ``sell`` e afins.

Duas licoes vindas do terminal de verdade estao codificadas aqui:

1. ``symbol_info_tick()`` **nao serve** como retrato do mercado: ele ja voltou
   com ``bid=0.0``, ``ask=0.0`` e ``last=42.11`` existindo book valido. Por
   isso a cotacao e' montada de duas fontes separadas - ``COPY_TICKS_INFO``
   para bid/ask e ``COPY_TICKS_TRADE`` para last/volume;
2. bid e ask zerados **nao sao preco**: sao ausencia de livro. Viram ``None``
   com estado ``NO_ACTIVE_BOOK``, e o ultimo negocio aparece a parte, com a
   idade dele. Preencher bid com o last seria inventar cotacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from ...models import BRT, Candle, CandleInvalidoError, Series
from ...settings import ConfigMarketData, carregar
from ..base import DataError
from ..cotacao import Cotacao
from ..mercado import MarketDataProvider
from ..status import Capacidades, StatusDados
from .simbolos import Resolucao, resolver
from .tempo import FUSO_PADRAO_DO_SERVIDOR, NormalizadorDeTempoDoBroker
from .terminal import TICKS_INFO, TICKS_TRADE, TIMEFRAMES, InfoTerminal, MT5Error, TerminalMT5

NOME = "metatrader"
TICKS_PARA_OLHAR = 500
JANELA_DE_TICKS_MIN = 30.0
STALE_PADRAO_S = 60.0


@dataclass(frozen=True)
class EventoDeCotacao:
    """O que ``COPY_TICKS_INFO`` entrega: os dois lados do livro."""

    bid: Optional[float]
    ask: Optional[float]
    ts: Optional[datetime]

    @property
    def tem_livro(self) -> bool:
        return self.bid is not None and self.ask is not None

    @property
    def spread(self) -> Optional[float]:
        # so existe quando os DOIS lados sao validos e positivos
        if not self.tem_livro:
            return None
        return self.ask - self.bid


@dataclass(frozen=True)
class EventoDeNegocio:
    """O que ``COPY_TICKS_TRADE`` entrega: o negocio fechado."""

    last: Optional[float]
    volume: Optional[float]
    ts: Optional[datetime]


class MetaTraderMarketDataProvider(MarketDataProvider):
    """Cotacao e candles reais do terminal da Genial. Nao envia ordem."""

    nome = NOME

    def __init__(self, config: Optional[ConfigMarketData] = None,
                 terminal: Optional[TerminalMT5] = None, relogio=None, log=None):
        from ...core.log import RegistradorNulo

        self.config = config or carregar()
        self.terminal = terminal or TerminalMT5(self.config.mt5_terminal_path)
        self.tempo = NormalizadorDeTempoDoBroker(
            fuso_do_servidor=self.config.mt5_fuso_do_servidor or FUSO_PADRAO_DO_SERVIDOR)
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self.log = log or RegistradorNulo()

        self._info: Optional[InfoTerminal] = None
        self._resolvidos: dict[str, Resolucao] = {}
        self._livro_por_simbolo: dict[str, bool] = {}

        # capacidades declaradas: o que foi verificado no terminal de verdade.
        # market_depth NAO entra aqui - ele e' detectado por simbolo
        self.capacidades = Capacidades(
            candles_historicos=True,
            cotacao=True,
            cotacao_em_tempo_real=True,
            ticks_em_tempo_real=True,
            livro_de_ofertas=False,     # detectado sob demanda, nunca presumido
            intradiario_1m=True,
            timeframes=tuple(TIMEFRAMES),
            atraso_tipico_s=0.0,        # feed do terminal: sem atraso declarado
            trading=False,              # PROIBIDO nesta fase, e sem metodo para isso
        )

    # ------------------------------------------------------------------
    # conexao
    # ------------------------------------------------------------------
    def conectar(self) -> InfoTerminal:
        """Liga no terminal ja aberto. Sem credencial: quem autentica e' voce."""
        info = self.terminal.conectar()
        self._info = info
        if info.conectado:
            self.log.info(NOME, "terminal conectado",
                          empresa=info.empresa, servidor=info.servidor)
        else:
            self.log.erro(NOME, f"terminal nao conectado: {info.motivo}")
        return info

    def info_do_terminal(self, recarregar: bool = False) -> InfoTerminal:
        if self._info is None or recarregar:
            return self.conectar()
        return self._info

    @property
    def disponivel(self) -> bool:
        return self.terminal.disponivel

    # ------------------------------------------------------------------
    # simbolos
    # ------------------------------------------------------------------
    def resolver_simbolo(self, symbol: str) -> Resolucao:
        """Exata primeiro; ambiguidade e ausencia sao erro, nunca escolha."""
        chave = symbol.strip().upper()
        if chave in self._resolvidos:
            return self._resolvidos[chave]

        self._exigir_terminal()
        resolucao = resolver(chave, self.terminal.simbolos(),
                             permitir_aproximado=self.config.mt5_resolucao_aproximada)
        self.terminal.selecionar(resolucao.resolvido)
        self._resolvidos[chave] = resolucao
        self.log.info(NOME, f"simbolo resolvido: {chave} -> {resolucao.resolvido}",
                      exato=resolucao.exato)
        return resolucao

    def simbolos(self) -> tuple[str, ...]:
        try:
            self._exigir_terminal()
            return self.terminal.simbolos()
        except DataError:
            return ()

    # ------------------------------------------------------------------
    # cotacao: duas fontes, nunca symbol_info_tick
    # ------------------------------------------------------------------
    def evento_de_cotacao(self, symbol: str) -> EventoDeCotacao:
        """Bid/ask do ultimo tick de COTACAO com livro valido."""
        for tick in self._ultimos_ticks(symbol, TICKS_INFO):
            bid, ask = _preco(tick.get("bid")), _preco(tick.get("ask"))
            if bid is not None and ask is not None:
                return EventoDeCotacao(bid, ask, self._momento(tick))
        return EventoDeCotacao(None, None, None)

    def evento_de_negocio(self, symbol: str) -> EventoDeNegocio:
        """Last/volume do ultimo tick de NEGOCIO com preco valido."""
        for tick in self._ultimos_ticks(symbol, TICKS_TRADE):
            last = _preco(tick.get("last"))
            if last is not None:
                volume = tick.get("volume_real") or tick.get("volume")
                return EventoDeNegocio(last, _numero(volume), self._momento(tick))
        return EventoDeNegocio(None, None, None)

    def cotacao(self, symbol: str) -> Cotacao:
        """O retrato consolidado - com os dois relogios separados."""
        resolucao = self.resolver_simbolo(symbol)
        alvo = resolucao.resolvido
        agora = self._relogio()

        cotacao_evt = self.evento_de_cotacao(alvo)
        negocio_evt = self.evento_de_negocio(alvo)
        status = self._status_da_cotacao(cotacao_evt, negocio_evt, agora)

        referencia = cotacao_evt.ts or negocio_evt.ts or agora
        idade = max((agora - referencia).total_seconds(), 0.0)

        return Cotacao(
            symbol=alvo,
            timestamp=referencia,
            source=self.nome,
            status=status,
            last=negocio_evt.last,
            bid=cotacao_evt.bid,          # None quando o livro esta zerado
            ask=cotacao_evt.ask,
            volume=negocio_evt.volume,
            data_age=idade,
            lida_em=agora,
            quote_timestamp=cotacao_evt.ts,
            trade_timestamp=negocio_evt.ts,
            detalhe=("" if cotacao_evt.tem_livro
                     else "bid/ask zerados no terminal: sem livro ativo"),
        )

    def _status_da_cotacao(self, cot: EventoDeCotacao, neg: EventoDeNegocio,
                           agora: datetime) -> StatusDados:
        """`initialize() == True` nao basta para dizer ONLINE."""
        info = self.info_do_terminal()
        if not info.conectado:
            return StatusDados.OFFLINE
        if cot.ts is None and neg.ts is None:
            return StatusDados.OFFLINE

        mais_novo = max([t for t in (cot.ts, neg.ts) if t is not None])
        idade = (agora - mais_novo).total_seconds()
        limite = self.config.mt5_stale_s or STALE_PADRAO_S

        if idade > limite:
            # dado parado com mercado fechado e' o esperado, nao defeito
            return (StatusDados.MARKET_CLOSED if not _no_pregao(agora)
                    else StatusDados.STALE)
        if not cot.tem_livro:
            return StatusDados.NO_ACTIVE_BOOK
        return StatusDados.ONLINE

    # ------------------------------------------------------------------
    # candles
    # ------------------------------------------------------------------
    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        """Candles reais - **somente os fechados**."""
        if timeframe not in TIMEFRAMES:
            raise DataError(
                f"timeframe {timeframe} nao mapeado para o MT5 "
                f"(disponiveis: {', '.join(TIMEFRAMES)})")

        resolucao = self.resolver_simbolo(symbol)
        quantidade = self._quantidade(timeframe, dias)
        try:
            bruto = self.terminal.candles(resolucao.resolvido, timeframe, quantidade)
        except MT5Error as e:
            self.log.erro(NOME, f"candles {symbol} {timeframe}: {e}")
            raise DataError(str(e)) from e

        candles = [c for c in (self._candle(linha) for linha in bruto) if c is not None]
        fechados = self.apenas_fechados(candles, timeframe)
        if not fechados:
            raise DataError(
                f"{resolucao.resolvido} {timeframe}: nenhum candle FECHADO disponivel "
                f"({len(candles)} recebido(s), todos em formacao)")
        return Series(resolucao.resolvido, timeframe, fechados)

    def apenas_fechados(self, candles: Sequence[Candle],
                        timeframe: str, agora: Optional[datetime] = None) -> list[Candle]:
        """Descarta o candle em formacao - pela hora, nao por ``[:-1]``.

        Cortar o ultimo as cegas joga fora um candle fechado sempre que a
        consulta cai logo depois da virada do periodo. A conta certa e': o
        candle so esta fechado quando o periodo dele **ja terminou**.
        """
        if not candles:
            return []
        instante = agora or self._relogio()
        duracao = _duracao_em_segundos(timeframe)
        return [c for c in candles
                if (c.ts + timedelta(seconds=duracao)) <= instante]

    # ------------------------------------------------------------------
    # estado e capacidades
    # ------------------------------------------------------------------
    def status(self, symbol: str = "", timeframe: str = "1m") -> StatusDados:
        try:
            return self.cotacao(symbol or "PETR4").status
        except DataError:
            return StatusDados.OFFLINE

    def livro_disponivel(self, symbol: str) -> bool:
        """Capacidade **detectada** no terminal, nunca declarada por otimismo."""
        alvo = self.resolver_simbolo(symbol).resolvido
        if alvo not in self._livro_por_simbolo:
            try:
                self._livro_por_simbolo[alvo] = self.terminal.livro_disponivel(alvo)
            except Exception:
                self._livro_por_simbolo[alvo] = False
        return self._livro_por_simbolo[alvo]

    def capacidades_de(self, symbol: str) -> Capacidades:
        """As capacidades com o livro de ofertas ja verificado para o ativo."""
        return self.capacidades.com(livro_de_ofertas=self.livro_disponivel(symbol))

    # ------------------------------------------------------------------
    def _exigir_terminal(self) -> InfoTerminal:
        info = self.info_do_terminal()
        if not info.conectado:
            raise DataError(
                f"TERMINAL OFFLINE: {info.motivo or 'o MetaTrader nao esta conectado'}. "
                "Abra o terminal da Genial e autentique antes de rodar o Cashinho")
        return info

    def _ultimos_ticks(self, symbol: str, tipo: str) -> list[dict]:
        """Ticks da janela recente, do mais novo para o mais antigo."""
        agora = self._relogio()
        desde = self.tempo.agora_no_servidor(agora) - timedelta(minutes=JANELA_DE_TICKS_MIN)
        try:
            ticks = self.terminal.ticks(symbol, desde.replace(tzinfo=None),
                                        TICKS_PARA_OLHAR, tipo)
        except MT5Error as e:
            self.log.erro(NOME, f"ticks {symbol} ({tipo}): {e}")
            return []
        return list(reversed(ticks))

    def _momento(self, tick: dict) -> Optional[datetime]:
        """O relogio do tick, normalizado. Prefere o campo em milissegundos."""
        if tick.get("time_msc"):
            return self.tempo.de_epoch_ms(tick["time_msc"])
        if tick.get("time"):
            return self.tempo.de_epoch(tick["time"])
        return None

    def _candle(self, linha: dict) -> Optional[Candle]:
        try:
            ts = self.tempo.de_epoch(linha["time"])
            volume = linha.get("real_volume") or linha.get("tick_volume") or 0.0
            return Candle(ts, float(linha["open"]), float(linha["high"]),
                          float(linha["low"]), float(linha["close"]), float(volume))
        except (KeyError, TypeError, ValueError, CandleInvalidoError):
            return None

    def _quantidade(self, timeframe: str, dias: int) -> int:
        por_dia = {"1m": 400, "5m": 80, "15m": 28, "30m": 14, "60m": 8, "1d": 1}
        return max(int(por_dia.get(timeframe, 100) * max(dias, 1)) + 2, 10)

    def para_dict(self) -> dict:
        info = self._info or InfoTerminal(False, motivo="ainda nao conectado")
        return {
            "provedor": self.nome,
            "capacidades": self.capacidades.para_dict(),
            "terminal": info.para_dict(),      # sem login, saldo ou patrimonio
            "fuso": self.tempo.para_dict(),
        }


def _preco(valor: Any) -> Optional[float]:
    """Preco valido, ou ``None``. **Zero nunca e' preco.**"""
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def _numero(valor: Any) -> Optional[float]:
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def _duracao_em_segundos(timeframe: str) -> float:
    from ...core.mtf.timeframes import parse_timeframe

    tf = parse_timeframe(timeframe)
    return (tf.duracao_minutos(375) if tf.sessao_inteira else tf.minutos) * 60


def _no_pregao(instante: datetime) -> bool:
    """Primeira aproximacao: sessao regular da B3, sem calendario de feriado.

    LIMITE CONHECIDO: nao conhece feriado. Num feriado, dado parado aparece
    como STALE em vez de MARKET_CLOSED - conservador na direcao certa (avisa
    demais, nunca de menos).
    """
    from ...core.mtf.session import Sessao

    return Sessao().contem(instante)
