"""Motor multi-timeframe com protecao contra lookahead.

Uso tipico::

    engine = MTFEngine(MTFConfig.padrao())
    engine.alimentar(serie_1m)              # o resto e' reamostrado daqui
    vista = engine.em(agora)                # fotografia do mercado nesse instante

    tendencia = vista.serie_da_camada("tendencia")   # so candles fechados
    ultimo_60m = vista.camada("contexto")            # levanta se ainda nao fechou

Toda leitura passa por um instante de referencia (``vista``). Barras cujo
fechamento e' posterior a esse instante simplesmente nao existem para quem
consulta - e tentar alcanca-las levanta :class:`LookaheadError`.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Iterator, Optional

from ...models import BRT, Candle, Series
from .config import MTFConfig
from .errors import DadosInsuficientesError, LookaheadError, MTFError
from .resample import para_bars, reamostrar
from .session import Sessao
from .timeframes import Bar, bars_para_series, parse_timeframe, rotulo_canonico


def _normaliza_instante(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=BRT)
    return ts.astimezone(BRT)


def _hhmm(ts: datetime) -> str:
    return ts.astimezone(BRT).strftime("%d/%m %H:%M")


class MTFEngine:
    """Mantem as series alinhadas e entrega fotografias sem futuro."""

    def __init__(self, config: Optional[MTFConfig] = None, symbol: str = ""):
        self.config = config or MTFConfig.padrao()
        self.symbol = symbol
        self._serie_base: Optional[Series] = None
        self._bars: dict[str, list[Bar]] = {}
        self._fins: dict[str, list[datetime]] = {}
        self._injetados: set[str] = set()

    # ------------------------------------------------------------------
    # alimentacao
    # ------------------------------------------------------------------
    @property
    def sessao(self) -> Sessao:
        return self.config.sessao

    def alimentar(self, serie_base: Series) -> "MTFEngine":
        """Carrega a serie do timeframe base e deriva todas as camadas."""
        base = self.config.tf_base
        if serie_base.timeframe and rotulo_canonico(serie_base.timeframe) != base.rotulo:
            raise MTFError(
                f"serie base em {serie_base.timeframe}, mas a configuracao usa base {base.rotulo}"
            )
        self.symbol = self.symbol or serie_base.symbol
        self._serie_base = serie_base
        self._guardar(
            base.rotulo,
            para_bars(serie_base, base, self.sessao, self.config.rotulagem),
            injetado=False,
        )
        for rotulo in self.config.timeframes():
            if rotulo == base.rotulo or rotulo in self._injetados:
                continue
            self._guardar(rotulo, self._reamostra(rotulo), injetado=False)
        return self

    def injetar(self, timeframe: str, serie: Series) -> "MTFEngine":
        """Usa uma serie pronta para um timeframe, em vez de reamostrar.

        Serve para feeds que ja entregam o timeframe maior - e para testes.
        A serie injetada pode conter um candle ainda em formacao: o motor
        detecta isso pela janela da sessao e bloqueia a leitura.
        """
        rotulo = rotulo_canonico(timeframe)
        self._guardar(
            rotulo,
            para_bars(serie, rotulo, self.sessao, self.config.rotulagem),
            injetado=True,
        )
        self.symbol = self.symbol or serie.symbol
        return self

    def _guardar(self, rotulo: str, bars: list[Bar], injetado: bool) -> None:
        bars = sorted(bars, key=lambda b: b.fim)
        self._bars[rotulo] = bars
        self._fins[rotulo] = [b.fim for b in bars]
        if injetado:
            self._injetados.add(rotulo)

    def _reamostra(self, rotulo: str) -> list[Bar]:
        if self._serie_base is None:
            return []
        return reamostrar(
            self._serie_base,
            rotulo,
            base=self.config.tf_base,
            sessao=self.sessao,
            rotulagem=self.config.rotulagem,
            descartar_fora_da_sessao=self.config.descartar_fora_da_sessao,
        )

    def barras(self, timeframe: str) -> list[Bar]:
        """Todas as barras conhecidas de um timeframe (inclusive a em formacao).

        Timeframes nao configurados sao reamostrados sob demanda, desde que
        sejam multiplos do timeframe base.
        """
        rotulo = rotulo_canonico(timeframe)
        if rotulo not in self._bars:
            tf = parse_timeframe(rotulo)
            if not tf.eh_multiplo_de(self.config.tf_base):
                raise MTFError(
                    f"{rotulo} nao e' multiplo da base {self.config.tf_base.rotulo}"
                )
            self._guardar(rotulo, self._reamostra(rotulo), injetado=False)
        return self._bars[rotulo]

    def timeframes_carregados(self) -> list[str]:
        return sorted(self._bars)

    # ------------------------------------------------------------------
    # leitura
    # ------------------------------------------------------------------
    def em(self, ts: datetime) -> "MTFVista":
        """Fotografia do mercado no instante ``ts``."""
        return MTFVista(self, _normaliza_instante(ts))

    def agora(self) -> "MTFVista":
        """Fotografia no fechamento do ultimo candle base conhecido."""
        base = self.barras(self.config.tf_base.rotulo)
        if not base:
            raise DadosInsuficientesError("nenhum candle base carregado")
        return self.em(base[-1].fim)

    def replay(
        self, desde: Optional[datetime] = None, ate: Optional[datetime] = None
    ) -> Iterator["MTFVista"]:
        """Percorre a serie base candle a candle, uma vista por fechamento.

        E' o modo correto de fazer backtest: em cada passo a vista so enxerga
        o que ja tinha fechado naquele instante.
        """
        base = self.barras(self.config.tf_base.rotulo)
        d = _normaliza_instante(desde) if desde else None
        a = _normaliza_instante(ate) if ate else None
        for bar in base:
            if d and bar.fim < d:
                continue
            if a and bar.fim > a:
                break
            yield self.em(bar.fim)


class MTFVista:
    """O mercado como ele era em um instante - sem nenhum candle do futuro."""

    __slots__ = ("_engine", "instante")

    def __init__(self, engine: MTFEngine, instante: datetime):
        self._engine = engine
        self.instante = instante

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        return f"<MTFVista {self._engine.symbol or '?'} em {_hhmm(self.instante)}>"

    @property
    def config(self) -> MTFConfig:
        return self._engine.config

    # -- acesso seguro ---------------------------------------------------
    def barras_fechadas(self, timeframe: str) -> list[Bar]:
        """Barras ja fechadas no instante da vista (pode vir vazio)."""
        rotulo = rotulo_canonico(timeframe)
        bars = self._engine.barras(rotulo)
        corte = bisect_right(self._engine._fins[rotulo], self.instante)
        return bars[:corte]

    def fechados(self, timeframe: str) -> Series:
        """Serie pronta para os indicadores, so com candles fechados."""
        rotulo = rotulo_canonico(timeframe)
        return bars_para_series(self._engine.symbol, rotulo, self.barras_fechadas(rotulo))

    def ultima_barra(self, timeframe: str) -> Bar:
        """Ultima barra fechada. Levanta se a unica disponivel ainda esta em formacao."""
        rotulo = rotulo_canonico(timeframe)
        fechadas = self.barras_fechadas(rotulo)
        if fechadas:
            return fechadas[-1]
        self._explica_ausencia(rotulo)

    def ultimo(self, timeframe: str) -> Candle:
        """Candle mais recente ja fechado no timeframe."""
        return self.ultima_barra(timeframe).candle

    def camada(self, papel: str) -> Candle:
        """Candle fechado mais recente da camada configurada (ex.: ``"contexto"``)."""
        return self.ultimo(self.config.timeframe(papel).rotulo)

    def serie_da_camada(self, papel: str) -> Series:
        return self.fechados(self.config.timeframe(papel).rotulo)

    def snapshot(self) -> dict[str, Optional[Candle]]:
        """Ultimo candle fechado de cada camada; ``None`` onde ainda nao fechou."""
        saida: dict[str, Optional[Candle]] = {}
        for papel in self.config.papeis():
            try:
                saida[papel] = self.camada(papel)
            except MTFError:
                saida[papel] = None
        return saida

    def pronta(self, minimo_por_camada: int = 1) -> bool:
        """Todas as camadas ja tem candles fechados suficientes?"""
        return all(
            len(self.barras_fechadas(self.config.timeframe(p).rotulo)) >= minimo_por_camada
            for p in self.config.papeis()
        )

    # -- acesso explicito ao que ainda nao fechou -------------------------
    def em_formacao(self, timeframe: str) -> Optional[Bar]:
        """Barra em formacao no instante da vista, se houver.

        Acesso deliberadamente separado: usar isto e' assumir que voce sabe
        que o candle esta incompleto (ex.: acompanhar o candle de gatilho ao
        vivo). Nunca alimente indicadores de timeframe maior com ele.
        """
        rotulo = rotulo_canonico(timeframe)
        for bar in self._engine.barras(rotulo):
            if bar.inicio <= self.instante < bar.fim:
                return bar
        return None

    # -- erros -----------------------------------------------------------
    def _explica_ausencia(self, rotulo: str) -> None:
        formando = self.em_formacao(rotulo)
        if formando is not None:
            raise LookaheadError(
                f"{rotulo}: o candle iniciado em {_hhmm(formando.inicio)} so fecha as "
                f"{_hhmm(formando.fim)}, e a consulta foi feita as {_hhmm(self.instante)}. "
                f"Usar esse candle agora seria ler o futuro - espere o fechamento ou use "
                f"em_formacao('{rotulo}') se voce realmente quer o candle parcial."
            )
        futuras = [b for b in self._engine.barras(rotulo) if b.inicio > self.instante]
        if futuras:
            raise LookaheadError(
                f"{rotulo}: nenhum candle fechado ate {_hhmm(self.instante)}; o proximo "
                f"so comeca em {_hhmm(futuras[0].inicio)} e fecha as {_hhmm(futuras[0].fim)}."
            )
        raise DadosInsuficientesError(
            f"{rotulo}: nenhum candle carregado ate {_hhmm(self.instante)}."
        )
