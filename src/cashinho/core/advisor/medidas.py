"""O que se mede em cada timeframe - so com candles ja fechados.

Cada medida devolve o numero **e** a frase que o explica. Medida que nao da
para calcular volta como ``None``, nunca como zero: zero e' uma afirmacao
sobre o mercado, ausencia de dado nao e'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Optional, Sequence

from ...indicators.core import atr
from ...models import Series
from ..structure.models import MarketStructure, Regime, TipoEvento

MIN_CANDLES = 20


@dataclass(frozen=True)
class Medida:
    """Um numero medido, com a leitura que o explica."""

    valor: Optional[float]
    leitura: str

    @property
    def disponivel(self) -> bool:
        return self.valor is not None

    def para_dict(self) -> dict:
        return {"valor": None if self.valor is None else round(self.valor, 4),
                "leitura": self.leitura, "disponivel": self.disponivel}


@dataclass(frozen=True)
class MedidasDoTimeframe:
    """O retrato de um timeframe no instante analisado."""

    timeframe: str
    candles: int
    eficiencia: Medida          # quanto do movimento e' direcional (0..1)
    volatilidade_pct: Medida    # ATR em % do preco
    volume_relativo: Medida     # volume recente sobre a media
    spread_relativo: Medida     # spread / amplitude tipica (None sem book)
    regime: Optional[Regime] = None
    forca_da_tendencia: Optional[float] = None   # 0..1, da propria estrutura
    falsos_rompimentos: int = 0
    rompimentos: int = 0
    pivos: int = 0
    estabilidade: Medida = field(
        default_factory=lambda: Medida(None, "sem janelas suficientes"))

    @property
    def amostra_suficiente(self) -> bool:
        return self.candles >= MIN_CANDLES

    @property
    def taxa_de_falso_rompimento(self) -> Optional[float]:
        total = self.rompimentos + self.falsos_rompimentos
        if total == 0:
            return None
        return self.falsos_rompimentos / total

    def para_dict(self) -> dict:
        return {
            "timeframe": self.timeframe, "candles": self.candles,
            "eficiencia": self.eficiencia.para_dict(),
            "volatilidade_pct": self.volatilidade_pct.para_dict(),
            "volume_relativo": self.volume_relativo.para_dict(),
            "spread_relativo": self.spread_relativo.para_dict(),
            "estabilidade": self.estabilidade.para_dict(),
            "regime": self.regime.value if self.regime else None,
            "forca_da_tendencia": self.forca_da_tendencia,
            "rompimentos": self.rompimentos,
            "falsos_rompimentos": self.falsos_rompimentos,
            "taxa_de_falso_rompimento": self.taxa_de_falso_rompimento,
            "pivos": self.pivos,
        }


# ---------------------------------------------------------------------------
# as medidas
# ---------------------------------------------------------------------------


def eficiencia(serie: Series, janela: int = 30) -> Medida:
    """Razao de eficiencia: quanto do caminho andado virou deslocamento.

    E' a medida de **ruido** deste modulo. Um mercado que sobe 1 real em linha
    reta tem eficiencia perto de 1; um que sobe o mesmo 1 real balancando tem
    eficiencia perto de 0. Timeframe com eficiencia baixa e' timeframe em que
    o preco se mexe muito para chegar a lugar nenhum - e' ali que o stop
    morre de graca.
    """
    fechamentos = serie.closes[-(janela + 1):]
    if len(fechamentos) < 6:
        return Medida(None, "candles insuficientes para medir ruido")

    deslocamento = abs(fechamentos[-1] - fechamentos[0])
    caminho = sum(abs(b - a) for a, b in zip(fechamentos, fechamentos[1:]))
    if caminho <= 0:
        return Medida(None, "preco parado na janela")

    razao = deslocamento / caminho
    if razao >= 0.5:
        leitura = f"movimento direcional ({razao:.0%} do caminho virou deslocamento)"
    elif razao >= 0.25:
        leitura = f"ruido moderado ({razao:.0%})"
    else:
        leitura = f"muito ruido: {razao:.0%} do caminho vira deslocamento"
    return Medida(razao, leitura)


def volatilidade(serie: Series, periodo: int = 14) -> Medida:
    """ATR como percentual do preco - a amplitude tipica do candle."""
    if len(serie) < periodo + 1:
        return Medida(None, "candles insuficientes para o ATR")
    valores = atr(serie.highs, serie.lows, serie.closes, periodo)
    ultimo = valores[-1] if valores else None
    preco = serie.price
    if ultimo is None or not preco:
        return Medida(None, "ATR indisponivel")
    pct = ultimo / preco * 100
    return Medida(pct, f"amplitude tipica de {pct:.2f}% do preco por candle")


def volume_relativo(serie: Series, periodo: int = 20) -> Medida:
    """Volume dos ultimos candles sobre a media da janela."""
    volumes = serie.volumes
    if len(volumes) < periodo + 1:
        return Medida(None, "candles insuficientes para comparar volume")
    janela = volumes[-periodo:]
    media = mean(janela)
    if media <= 0:
        return Medida(None, "volume zerado na janela")
    razao = volumes[-1] / media
    return Medida(razao, f"volume do ultimo candle em {razao:.2f}x a media")


def spread_relativo(spread: Optional[float], serie: Series,
                    periodo: int = 14) -> Medida:
    """Quanto do movimento tipico o spread come.

    Sem book (CSV, sintetico, brapi) isto e' **indisponivel** - e indisponivel
    reduz a confianca, em vez de virar zero.
    """
    if spread is None:
        return Medida(None, "sem book: spread nao informado por esta fonte")
    amplitude = volatilidade(serie, periodo)
    if not amplitude.disponivel or not serie.price:
        return Medida(None, "sem amplitude para comparar o spread")
    atr_em_reais = amplitude.valor / 100 * serie.price
    if atr_em_reais <= 0:
        return Medida(None, "amplitude zerada")
    razao = spread / atr_em_reais
    if razao <= 0.05:
        leitura = f"spread consome {razao:.1%} da amplitude do candle"
    elif razao <= 0.15:
        leitura = f"spread relevante: {razao:.1%} da amplitude"
    else:
        leitura = f"spread come {razao:.1%} da amplitude - custo alto neste timeframe"
    return Medida(razao, leitura)


def estabilidade(serie: Series, janela: int = 30, blocos: int = 3) -> Medida:
    """A eficiencia se manteve nas ultimas janelas, ou variou muito?

    Timeframe cujo comportamento oscila a cada janela nao merece recomendacao
    firme, por melhor que esteja agora.
    """
    necessario = janela * blocos + 1
    if len(serie) < necessario:
        return Medida(None, f"precisa de {necessario} candles para medir estabilidade")

    amostras = []
    for i in range(blocos):
        fim = len(serie) - i * janela
        pedaco = Series(serie.symbol, serie.timeframe, serie.candles[fim - janela - 1:fim])
        medida = eficiencia(pedaco, janela)
        if medida.disponivel:
            amostras.append(medida.valor)
    if len(amostras) < 2:
        return Medida(None, "janelas insuficientes para medir estabilidade")

    desvio = pstdev(amostras)
    # desvio de 0 = identico entre janelas; 0.25 ja e' bastante instavel
    nota = max(0.0, 1.0 - desvio / 0.25)
    return Medida(nota, f"eficiencia variou {desvio:.2f} entre as ultimas "
                        f"{len(amostras)} janelas")


def medir(serie: Series, estrutura: Optional[MarketStructure] = None,
          spread: Optional[float] = None) -> MedidasDoTimeframe:
    """Todas as medidas de um timeframe, de uma vez."""
    rompimentos = falsos = pivos = 0
    regime = None
    forca = None
    if estrutura is not None:
        # acesso direto, sem getattr com padrao: se a estrutura mudar de
        # campo, isto tem que explodir aqui e nao zerar metade do score em
        # silencio - foi exatamente o que aconteceu na primeira versao
        regime = estrutura.tendencia.regime
        forca = estrutura.tendencia.forca
        rompimentos = sum(1 for e in estrutura.eventos
                          if e.tipo is TipoEvento.ROMPIMENTO)
        falsos = sum(1 for e in estrutura.eventos
                     if e.tipo is TipoEvento.POSSIVEL_FALSO_ROMPIMENTO)
        pivos = len(estrutura.pivos)

    return MedidasDoTimeframe(
        timeframe=serie.timeframe,
        candles=len(serie),
        eficiencia=eficiencia(serie),
        volatilidade_pct=volatilidade(serie),
        volume_relativo=volume_relativo(serie),
        spread_relativo=spread_relativo(spread, serie),
        regime=regime,
        forca_da_tendencia=forca,
        rompimentos=rompimentos,
        falsos_rompimentos=falsos,
        pivos=pivos,
        estabilidade=estabilidade(serie),
    )
