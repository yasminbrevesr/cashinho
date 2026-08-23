"""Market Replay: o pregao de novo, candle a candle, sem futuro nenhum.

A cada candle que fecha, o replay roda o caminho inteiro com **apenas o que
existia naquele instante**:

    fita -> multi-timeframe -> Strategy -> Opportunity -> Score
         -> Auditor -> Risk Manager -> Paper Broker

A garantia contra look-ahead vem de duas pecas que ja existiam e de uma nova:

- :class:`FitaDeMercado` nao entrega candle a frente da posicao - nao ha
  metodo para isso;
- a vista do motor multi-timeframe so devolve barras ja fechadas naquele
  instante;
- o Paper Broker recebe **um** candle por vez, o atual, e nunca a serie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Iterator, Optional, Sequence

from ...models import BRT, Candle, Direction, Series, formata_dinheiro
from ..auditor.auditor import ContrarianAuditor
from ..auditor.pipeline import Pipeline, ResultadoFinal
from ..broker.modelos import Order, OrderType
from ..broker.paper import ConfigPaper, PaperBroker
from ..broker.risco import BrokerComRisco
from ..diario.registrador import BrokerComDiario
from ..diario.diario import DiarioDeTrades
from ..mtf import MTFConfig, MTFEngine
from ..oportunidade.engine import OpportunityEngine
from ..oportunidade.estrategia import EstrategiaOportunidade
from ..risk import RiskConfig, RiskManager, RiskState
from ..strategy.base import Strategy
from .eventos import EventoReplay, TipoEvento
from .fita import FitaDeMercado, fita_do_dia
from .velocidade import Relogio, Velocidade


@dataclass(frozen=True)
class ReplayConfig:
    """O que o usuario escolhe antes de comecar."""

    symbol: str = "PETR4"
    dia: Optional[date] = None
    timeframe_base: str = "1m"
    velocidade: Velocidade = Velocidade.MAXIMA
    capital: float = 100_000.0
    risco_por_trade_pct: float = 1.0
    proteger_com_oco: bool = True
    minimo_para_analisar: int = 30  # candles antes de comecar a avaliar

    def __post_init__(self) -> None:
        if self.capital <= 0:
            raise ValueError("capital precisa ser maior que zero")
        if self.minimo_para_analisar < 1:
            raise ValueError("minimo_para_analisar precisa ser pelo menos 1")


@dataclass
class PassoReplay:
    """O que aconteceu em um candle."""

    indice: int
    candle: Candle
    resultado: Optional[ResultadoFinal] = None
    eventos: list[EventoReplay] = field(default_factory=list)
    ordens_executadas: int = 0

    @property
    def instante(self) -> datetime:
        return self.candle.ts


@dataclass
class EstadoReplay:
    """O acumulado do replay ate agora."""

    config: ReplayConfig
    fita: FitaDeMercado
    eventos: list[EventoReplay] = field(default_factory=list)
    passos: int = 0
    sinais: int = 0
    oportunidades: int = 0
    barrados_auditor: int = 0
    barrados_risco: int = 0
    entradas: int = 0
    saidas: int = 0

    @property
    def progresso(self) -> float:
        return self.fita.progresso

    def para_dict(self) -> dict:
        return {
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe_base,
            "velocidade": self.config.velocidade.value,
            "passos": self.passos,
            "progresso": round(self.progresso, 4),
            "sinais": self.sinais,
            "oportunidades": self.oportunidades,
            "barrados_auditor": self.barrados_auditor,
            "barrados_risco": self.barrados_risco,
            "entradas": self.entradas,
            "saidas": self.saidas,
            "eventos": [e.para_dict() for e in self.eventos],
        }


class MarketReplay:
    """Reproduz um pregao e roda o pipeline como se fosse ao vivo."""

    def __init__(
        self,
        serie: Series,
        config: Optional[ReplayConfig] = None,
        estrategia: Optional[Strategy] = None,
        relogio: Optional[Relogio] = None,
    ):
        self.config = config or ReplayConfig(symbol=serie.symbol)
        self.fita = fita_do_dia(serie, self.config.dia)
        self.relogio = relogio or Relogio(self.config.velocidade)

        # o motor de alinhamento recebe a serie do DIA, e a vista so entrega
        # barras fechadas ate o instante pedido
        self.mtf = MTFEngine(
            MTFConfig(base=self.config.timeframe_base,
                      camadas={"context": "60m", "trend": "15m",
                               "setup": "5m", "trigger": self.config.timeframe_base}),
            symbol=self.config.symbol,
        ).alimentar(self.fita_completa())

        self.engine = OpportunityEngine()
        self.estrategia = estrategia or EstrategiaOportunidade(self.engine)
        self.auditor = ContrarianAuditor()
        self.risco = RiskManager(
            RiskConfig(capital=self.config.capital,
                       risco_por_trade_pct=self.config.risco_por_trade_pct),
            RiskState(capital_inicial=self.config.capital),
        )
        self.pipeline = Pipeline(self.estrategia, self.engine, self.auditor, self.risco)

        paper = PaperBroker(ConfigPaper(capital_inicial=self.config.capital),
                            relogio=lambda: self.fita.instante if self.fita.comecou
                            else datetime.now(BRT))
        self.diario = DiarioDeTrades()
        self.broker = BrokerComDiario(BrokerComRisco(paper, self.risco), self.diario)
        self._paper = paper

        self.estado = EstadoReplay(self.config, self.fita)
        self._posicao_aberta = False

    # ------------------------------------------------------------------
    def fita_completa(self) -> Series:
        """A serie do dia - usada so para montar o alinhamento de timeframes.

        Isto NAO e' um vazamento: o motor multi-timeframe nunca devolve barra
        que ainda nao fechou no instante consultado, e e' esse instante que o
        replay controla.
        """
        return self.fita._serie

    # ------------------------------------------------------------------
    def passo(self) -> PassoReplay:
        """Avanca um candle e roda tudo o que existe naquele instante."""
        candle = self.fita.avancar()
        indice = self.fita.posicao
        passo = PassoReplay(indice=indice, candle=candle)
        self.estado.passos += 1

        # 1) a corretora recebe SO o candle atual
        executadas = self.broker.processar(self.config.symbol, candle)
        passo.ordens_executadas = len(executadas)
        for ordem in executadas:
            passo.eventos.append(self._evento_de_ordem(ordem, indice))

        posicionado = bool(self.broker.get_positions(self.config.symbol))
        if self._posicao_aberta and not posicionado:
            self.estado.saidas += 1
        self._posicao_aberta = posicionado

        # 2) o pipeline, com a vista daquele instante
        if indice + 1 >= self.config.minimo_para_analisar and not posicionado:
            vista = self.mtf.em(candle.ts)
            resultado = self.pipeline.executar(vista, self.config.symbol, agora=candle.ts)
            passo.resultado = resultado
            passo.eventos.extend(self._eventos_do_pipeline(resultado, indice, candle))

            if resultado.aprovado:
                passo.eventos.extend(self._entrar(resultado, indice, candle))

        self.estado.eventos.extend(passo.eventos)
        return passo

    def executar(
        self,
        ate: Optional[int] = None,
        aoPasso: Optional[Callable[[PassoReplay], None]] = None,
    ) -> EstadoReplay:
        """Roda o replay ate o fim (ou ate ``ate`` candles), respeitando a velocidade."""
        limite = ate if ate is not None else self.fita.total
        while not self.fita.terminou and self.estado.passos < limite:
            passo = self.passo()
            if aoPasso is not None:
                aoPasso(passo)
            if not self.fita.terminou:
                self.relogio.esperar(self.config.timeframe_base)
        return self.estado

    def __iter__(self) -> Iterator[PassoReplay]:
        while not self.fita.terminou:
            yield self.passo()

    # ------------------------------------------------------------------
    def _eventos_do_pipeline(self, r: ResultadoFinal, indice: int,
                             candle: Candle) -> list[EventoReplay]:
        eventos: list[EventoReplay] = []
        sinal = r.signal
        if sinal is not None and sinal.action.acionavel:
            self.estado.sinais += 1
            eventos.append(EventoReplay(
                TipoEvento.SINAL, indice, candle.ts, candle.close,
                f"{sinal.action.value}: {sinal.setup}", sinal.action.direcao,
            ))
        if r.opportunity is not None and r.opportunity.acionavel:
            self.estado.oportunidades += 1

        parada = r.parou_em
        if parada is not None and parada.nome in ("Auditor", "Risk Manager"):
            if parada.nome == "Auditor":
                self.estado.barrados_auditor += 1
            else:
                self.estado.barrados_risco += 1
            eventos.append(EventoReplay(
                TipoEvento.BARRADO, indice, candle.ts, candle.close,
                f"{parada.nome}: {parada.detalhe}",
            ))
        return eventos

    def _entrar(self, r: ResultadoFinal, indice: int, candle: Candle) -> list[EventoReplay]:
        """Envia a entrada e a protecao ao Paper Broker."""
        op = r.opportunity
        decisao = r.decisao_de_risco
        eventos: list[EventoReplay] = []

        self.broker.anotar_contexto(
            self.config.symbol, oportunidade=op, auditoria=r.auditoria,
        )
        entrada = self.broker.place_order(Order(
            symbol=self.config.symbol, side=op.direction, tipo=OrderType.MARKET,
            quantidade=decisao.position_size, stop_referencia=op.stop,
            referencia="replay",
        ))
        if entrada.preco_executado is None:
            return eventos

        self.estado.entradas += 1
        self._posicao_aberta = True
        eventos.append(EventoReplay(
            TipoEvento.ENTRADA, indice, candle.ts, entrada.preco_executado,
            f"{op.direction.value} {entrada.quantidade} @ {entrada.preco_executado:.2f}"
            f" (score {op.score:.0f})", op.direction,
        ))
        eventos.append(EventoReplay(
            TipoEvento.STOP, indice, candle.ts, op.stop, f"stop em {op.stop:.2f}", op.direction,
        ))
        eventos.append(EventoReplay(
            TipoEvento.ALVO, indice, candle.ts, op.target, f"alvo em {op.target:.2f}", op.direction,
        ))

        if self.config.proteger_com_oco:
            lado = Direction.SHORT if op.direction is Direction.LONG else Direction.LONG
            self.broker.place_oco(
                Order(self.config.symbol, lado, OrderType.STOP_LOSS,
                      entrada.quantidade, preco_disparo=op.stop),
                Order(self.config.symbol, lado, OrderType.TAKE_PROFIT,
                      entrada.quantidade, preco_limite=op.target),
            )
        return eventos

    def _evento_de_ordem(self, ordem: Order, indice: int) -> EventoReplay:
        tipo = {
            OrderType.STOP_LOSS: TipoEvento.STOP,
            OrderType.TAKE_PROFIT: TipoEvento.ALVO,
        }.get(ordem.tipo, TipoEvento.SAIDA)
        return EventoReplay(
            TipoEvento.SAIDA, indice, ordem.executada_em or self.fita.instante,
            ordem.preco_executado or 0.0,
            f"saida por {ordem.tipo.value} @ {(ordem.preco_executado or 0):.2f}",
            ordem.side, {"tipo_original": tipo.value},
        )

    # ------------------------------------------------------------------
    @property
    def saldo(self):
        return self.broker.get_balance()

    def resumo(self) -> str:
        s = self.saldo
        return (
            f"{self.config.symbol} {self.config.timeframe_base} · "
            f"{self.estado.passos}/{self.fita.total} candles · "
            f"{self.estado.entradas} entrada(s) · "
            f"patrimonio {formata_dinheiro(s.patrimonio)}"
        )
