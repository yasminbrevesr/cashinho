"""O sistema de score - onze componentes, nenhum deles uma caixa-preta.

Cada componente devolve uma nota de 0 a 100 **e a frase que a explica**. O
score final e' a media ponderada, com pesos configuraveis. Nada e' escondido:
:class:`ScoreDetalhado` guarda nota, peso, contribuicao e leitura de cada
componente, e a tela mostra todos - inclusive os que puxaram para baixo.

Os pesos nao precisam somar 1: eles sao normalizados pela soma. Assim da para
dizer "tendencia pesa o dobro de fibonacci" sem ter que recalcular o resto.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Optional, Sequence

from ...indicators.core import ema
from ...indicators.momentum import macd as calcula_macd
from ...indicators.momentum import rsi as calcula_rsi
from ...indicators.volatility import atr_percentual
from ...indicators.volume import fluxo_direcional, volume_relativo, vwap_sessao
from ...models import Direction, Series, formata_dinheiro
from ..confluencia.estados import TriggerState, Vies
from ..confluencia.modelos import LeituraMultiTimeframe
from ..structure.models import MarketStructure, Regime


class PesosInvalidosError(ValueError):
    """Combinacao de pesos impossivel de usar."""


@dataclass(frozen=True)
class PesosScore:
    """Quanto cada componente vale. Configuravel, e normalizado pela soma."""

    tendencia: float = 1.5
    estrutura: float = 1.3
    gatilho: float = 1.3
    risco_retorno: float = 1.3
    medias: float = 1.0
    volume: float = 1.0
    suporte_resistencia: float = 1.0
    momentum: float = 0.9
    vwap: float = 0.9
    fibonacci: float = 0.7
    volatilidade: float = 0.7

    def __post_init__(self) -> None:
        for nome, valor in asdict(self).items():
            if valor < 0:
                raise PesosInvalidosError(f"peso de {nome} nao pode ser negativo ({valor})")
        if self.soma <= 0:
            raise PesosInvalidosError("ao menos um componente precisa ter peso maior que zero")

    @property
    def soma(self) -> float:
        return sum(asdict(self).values())

    def peso(self, chave: str) -> float:
        return float(asdict(self).get(chave, 0.0))

    def normalizados(self) -> dict[str, float]:
        soma = self.soma
        return {k: v / soma for k, v in asdict(self).items()}

    def atualizar(self, **campos: float) -> "PesosScore":
        desconhecidos = set(campos) - set(asdict(self))
        if desconhecidos:
            raise PesosInvalidosError(f"componentes desconhecidos: {', '.join(sorted(desconhecidos))}")
        return replace(self, **campos)

    def para_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: Mapping[str, Any]) -> "PesosScore":
        conhecidos = set(asdict(cls()))
        return cls(**{k: float(v) for k, v in dados.items() if k in conhecidos})


PESOS_PADRAO = PesosScore()

NOMES = {
    "tendencia": "Tendencia",
    "estrutura": "Estrutura",
    "volume": "Volume",
    "vwap": "VWAP",
    "medias": "Medias",
    "momentum": "Momentum",
    "volatilidade": "Volatilidade",
    "suporte_resistencia": "Suporte/Resistencia",
    "fibonacci": "Fibonacci",
    "gatilho": "Qualidade do gatilho",
    "risco_retorno": "Risco/Retorno",
}


@dataclass(frozen=True)
class ComponenteScore:
    """A nota de um componente e a leitura que a justifica."""

    chave: str
    nota: float  # 0..100
    leitura: str
    peso: float = 1.0
    detalhes: dict = field(default_factory=dict)

    @property
    def nome(self) -> str:
        return NOMES.get(self.chave, self.chave)

    def contribuicao(self, soma_dos_pesos: float) -> float:
        return self.nota * self.peso / soma_dos_pesos if soma_dos_pesos else 0.0


@dataclass(frozen=True)
class ScoreDetalhado:
    """O score final com o caminho inteiro ate ele."""

    componentes: tuple[ComponenteScore, ...]
    pesos: PesosScore = PESOS_PADRAO

    @property
    def soma_dos_pesos(self) -> float:
        return sum(c.peso for c in self.componentes)

    @property
    def total(self) -> float:
        """Media ponderada das notas, de 0 a 100."""
        soma = self.soma_dos_pesos
        if soma <= 0:
            return 0.0
        return round(sum(c.nota * c.peso for c in self.componentes) / soma, 1)

    def componente(self, chave: str) -> Optional[ComponenteScore]:
        for c in self.componentes:
            if c.chave == chave:
                return c
        return None

    def por_contribuicao(self) -> list[ComponenteScore]:
        soma = self.soma_dos_pesos
        return sorted(self.componentes, key=lambda c: -c.contribuicao(soma))

    def piores(self, quantos: int = 3) -> list[ComponenteScore]:
        """Os componentes que mais puxaram o score para baixo."""
        return sorted(self.componentes, key=lambda c: c.nota)[:quantos]

    def para_dict(self) -> dict:
        soma = self.soma_dos_pesos
        return {
            "total": self.total,
            "pesos": self.pesos.para_dict(),
            "componentes": [
                {
                    "chave": c.chave,
                    "nome": c.nome,
                    "nota": round(c.nota, 1),
                    "peso": c.peso,
                    "contribuicao": round(c.contribuicao(soma), 2),
                    "leitura": c.leitura,
                }
                for c in self.componentes
            ],
        }


# ---------------------------------------------------------------------------
# contexto: tudo o que os componentes precisam, calculado uma vez
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigScore:
    """Limiares dos componentes."""

    rsi_periodo: int = 14
    periodo_volume: int = 20
    atr_min_pct: float = 0.15
    atr_max_pct: float = 3.0
    atr_ideal_pct: float = 0.60
    volume_bom: float = 1.5
    fluxo_bom: float = 0.65
    rr_bom: float = 3.0
    distancia_esticada_atr: float = 2.0
    ema_curta: int = 9
    ema_media: int = 21
    ema_longa: int = 50


@dataclass
class ContextoScore:
    """Leituras prontas para os componentes - calculadas uma vez so."""

    direcao: Direction
    leitura: LeituraMultiTimeframe
    estrutura: MarketStructure
    serie_setup: Series
    serie_trigger: Series
    entry: float
    stop: float
    target: float
    cfg: ConfigScore = field(default_factory=ConfigScore)

    # preenchidos em montar_contexto
    vwap: Optional[float] = None
    vwap_sup: Optional[float] = None
    vwap_inf: Optional[float] = None
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None
    atr_pct: Optional[float] = None
    volume_relativo: Optional[float] = None
    fluxo: Optional[float] = None
    emas: tuple[Optional[float], Optional[float], Optional[float]] = (None, None, None)

    @property
    def alta(self) -> bool:
        return self.direcao is Direction.LONG

    @property
    def risco_por_acao(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def rr(self) -> float:
        risco = self.risco_por_acao
        return abs(self.target - self.entry) / risco if risco > 0 else 0.0

    @property
    def vies_alvo(self) -> Vies:
        return Vies.de_direcao(self.direcao)


def montar_contexto(
    direcao: Direction,
    leitura: LeituraMultiTimeframe,
    estrutura: MarketStructure,
    serie_setup: Series,
    serie_trigger: Series,
    entry: float,
    stop: float,
    target: float,
    cfg: ConfigScore = ConfigScore(),
) -> ContextoScore:
    """Calcula os indicadores uma unica vez e devolve o contexto do score."""
    closes = serie_setup.closes
    vw = vwap_sessao(serie_setup.candles)
    macd = calcula_macd(closes)
    return ContextoScore(
        direcao=direcao, leitura=leitura, estrutura=estrutura,
        serie_setup=serie_setup, serie_trigger=serie_trigger,
        entry=entry, stop=stop, target=target, cfg=cfg,
        vwap=vw.vwap[-1], vwap_sup=vw.banda_sup1[-1], vwap_inf=vw.banda_inf1[-1],
        rsi=calcula_rsi(closes, cfg.rsi_periodo)[-1],
        macd_hist=macd.hist[-1],
        atr_pct=atr_percentual(serie_setup.highs, serie_setup.lows, closes)[-1],
        volume_relativo=volume_relativo(serie_trigger.volumes, cfg.periodo_volume)[-1],
        fluxo=fluxo_direcional(serie_trigger.candles, cfg.periodo_volume),
        emas=(ema(closes, cfg.ema_curta)[-1], ema(closes, cfg.ema_media)[-1],
              ema(closes, cfg.ema_longa)[-1]),
    )


def _escala(valor: Optional[float], zero: float, cem: float) -> float:
    """Converte uma leitura em nota 0..100, saturando nas pontas."""
    if valor is None or cem == zero:
        return 0.0
    return max(0.0, min(100.0, (valor - zero) / (cem - zero) * 100.0))


def _clamp(nota: float) -> float:
    return round(max(0.0, min(100.0, nota)), 1)


# ---------------------------------------------------------------------------
# os onze componentes
# ---------------------------------------------------------------------------


def nota_tendencia(ctx: ContextoScore) -> ComponenteScore:
    trend = ctx.leitura.camada("trend")
    context = ctx.leitura.camada("context")
    alvo = ctx.vies_alvo

    if trend is None:
        return ComponenteScore("tendencia", 0.0, "camada de tendencia indisponivel")

    if trend.vies is alvo:
        nota = 60 + 40 * trend.forca
        leitura = f"{trend.timeframe} {trend.valor} a favor (forca {trend.forca:.2f})"
    elif trend.vies is Vies.NEUTRAL:
        nota, leitura = 45.0, f"{trend.timeframe} sem direcao definida"
    else:
        nota, leitura = 10.0, f"{trend.timeframe} {trend.valor} CONTRA a operacao"

    if context is not None:
        if context.vies is alvo:
            nota += 15 * context.forca
            leitura += f"; contexto {context.timeframe} tambem a favor"
        elif context.vies is not Vies.NEUTRAL:
            nota -= 20
            leitura += f"; contexto {context.timeframe} contra"
        else:
            leitura += f"; contexto {context.timeframe} neutro"
    return ComponenteScore("tendencia", _clamp(nota), leitura)


def nota_estrutura(ctx: ContextoScore) -> ComponenteScore:
    e = ctx.estrutura
    regime = e.tendencia.regime
    esperado = Regime.ALTA if ctx.alta else Regime.BAIXA
    contrario = Regime.BAIXA if ctx.alta else Regime.ALTA

    if regime is esperado:
        nota = 60 + 30 * e.tendencia.forca
        leitura = f"{e.tendencia.sequencia} a favor ({e.timeframe})"
    elif regime is Regime.LATERAL:
        nota, leitura = 40.0, f"estrutura lateral ({e.tendencia.sequencia})"
    else:
        nota, leitura = 15.0, f"estrutura {regime.value} contra a operacao"

    if e.swing_valido is not None and e.swing_valido.direcao is ctx.direcao:
        nota += 10
        leitura += f"; ultima perna de {e.swing_valido.amplitude_atr:.1f} ATR a favor"
    return ComponenteScore("estrutura", _clamp(nota), leitura)


def nota_volume(ctx: ContextoScore) -> ComponenteScore:
    vrel = ctx.volume_relativo
    fluxo = ctx.fluxo
    if vrel is None:
        return ComponenteScore("volume", 0.0, "sem media de volume ainda")

    nota = 40 + 0.4 * _escala(vrel, 0.8, ctx.cfg.volume_bom)
    leitura = f"{vrel:.2f}x a media no gatilho"
    if fluxo is not None:
        a_favor = fluxo if ctx.alta else (1.0 - fluxo)
        nota += 0.2 * _escala(a_favor, 0.45, ctx.cfg.fluxo_bom)
        leitura += f"; {a_favor * 100:.0f}% do volume recente no lado da operacao"
    return ComponenteScore("volume", _clamp(nota), leitura)


def nota_vwap(ctx: ContextoScore) -> ComponenteScore:
    if ctx.vwap is None:
        return ComponenteScore("vwap", 50.0, "VWAP indisponivel na serie")

    preco = ctx.entry
    acima = preco > ctx.vwap
    do_lado_certo = acima if ctx.alta else not acima
    banda = ctx.vwap_sup if ctx.alta else ctx.vwap_inf
    esticado = banda is not None and ((preco > banda) if ctx.alta else (preco < banda))

    if do_lado_certo and not esticado:
        nota = 90.0
        leitura = f"preco {formata_dinheiro(preco)} do lado certo da VWAP ({formata_dinheiro(ctx.vwap)})"
    elif do_lado_certo and esticado:
        nota = 55.0
        leitura = f"preco esticado alem da banda da VWAP ({formata_dinheiro(banda)})"
    else:
        nota = 25.0
        leitura = f"preco do lado errado da VWAP ({formata_dinheiro(ctx.vwap)})"
    return ComponenteScore("vwap", _clamp(nota), leitura)


def nota_medias(ctx: ContextoScore) -> ComponenteScore:
    curta, media, longa = ctx.emas
    if None in (curta, media, longa):
        return ComponenteScore("medias", 0.0, "medias ainda sem valor")

    empilhada = (curta > media > longa) if ctx.alta else (curta < media < longa)
    preco_ok = (ctx.entry > media) if ctx.alta else (ctx.entry < media)
    atr = ctx.estrutura.atr or 1e-9
    distancia = abs(ctx.entry - media) / atr

    if empilhada and preco_ok:
        nota = 85.0
        leitura = f"medias empilhadas a favor, preco do lado certo da EMA{ctx.cfg.ema_media}"
    elif empilhada:
        nota = 60.0
        leitura = f"medias empilhadas, mas preco atravessou a EMA{ctx.cfg.ema_media}"
    elif preco_ok:
        nota = 45.0
        leitura = "medias embaralhadas"
    else:
        nota = 20.0
        leitura = "medias embaralhadas e preco do lado errado"

    if distancia > ctx.cfg.distancia_esticada_atr:
        nota -= 15
        leitura += f"; preco a {distancia:.1f} ATR da media (esticado)"
    return ComponenteScore("medias", _clamp(nota), leitura)


def nota_momentum(ctx: ContextoScore) -> ComponenteScore:
    rsi, hist = ctx.rsi, ctx.macd_hist
    if rsi is None:
        return ComponenteScore("momentum", 0.0, "RSI ainda sem valor")

    # a favor sem estar no extremo: 55-70 numa compra e' o ideal
    if ctx.alta:
        nota = 100 - abs(rsi - 62) * 2.5
        exagerado = rsi > 78
    else:
        nota = 100 - abs(rsi - 38) * 2.5
        exagerado = rsi < 22
    leitura = f"RSI {rsi:.0f}"
    if exagerado:
        nota -= 20
        leitura += " (esticado)"

    if hist is not None:
        a_favor = hist > 0 if ctx.alta else hist < 0
        nota += 12 if a_favor else -12
        leitura += f"; MACD {'a favor' if a_favor else 'contra'}"
    return ComponenteScore("momentum", _clamp(nota), leitura)


def nota_volatilidade(ctx: ContextoScore) -> ComponenteScore:
    atr_pct = ctx.atr_pct
    cfg = ctx.cfg
    if atr_pct is None:
        return ComponenteScore("volatilidade", 0.0, "ATR ainda sem valor")

    if atr_pct < cfg.atr_min_pct:
        return ComponenteScore(
            "volatilidade", 15.0, f"ativo parado: ATR de {atr_pct:.2f}% (minimo {cfg.atr_min_pct:.2f}%)"
        )
    if atr_pct > cfg.atr_max_pct:
        return ComponenteScore(
            "volatilidade", 20.0, f"volatilidade excessiva: ATR de {atr_pct:.2f}%"
        )
    # nota maxima no ATR ideal, caindo para as bordas da faixa
    if atr_pct <= cfg.atr_ideal_pct:
        nota = 50 + 50 * (atr_pct - cfg.atr_min_pct) / max(cfg.atr_ideal_pct - cfg.atr_min_pct, 1e-9)
    else:
        nota = 100 - 50 * (atr_pct - cfg.atr_ideal_pct) / max(cfg.atr_max_pct - cfg.atr_ideal_pct, 1e-9)
    return ComponenteScore("volatilidade", _clamp(nota), f"ATR de {atr_pct:.2f}% do preco")


def nota_suporte_resistencia(ctx: ContextoScore) -> ComponenteScore:
    e = ctx.estrutura
    adiante = e.resistencia if ctx.alta else e.suporte
    atras = e.suporte if ctx.alta else e.resistencia
    atr = e.atr or 1e-9

    if adiante is None:
        nota, leitura = 70.0, "nenhuma zona mapeada no caminho do alvo"
    else:
        espaco = abs(adiante.mid - ctx.entry) / atr
        alvo_cabe = abs(ctx.target - ctx.entry) <= abs(adiante.mid - ctx.entry) * 1.05
        nota = _escala(espaco, 0.5, 4.0)
        leitura = (
            f"{espaco:.1f} ATR ate a {adiante.tipo} de {formata_dinheiro(adiante.mid)}"
            f"{'; o alvo cabe antes dela' if alvo_cabe else '; o ALVO passa por dentro dela'}"
        )
        if not alvo_cabe:
            nota -= 25

    if atras is not None:
        apoio = abs(ctx.entry - atras.mid) / atr
        if apoio <= 1.0:
            nota += 15
            leitura += f"; apoio proximo em {formata_dinheiro(atras.mid)}"
    return ComponenteScore("suporte_resistencia", _clamp(nota), leitura)


def nota_fibonacci(ctx: ContextoScore) -> ComponenteScore:
    fib = ctx.estrutura.fib
    if fib is None:
        return ComponenteScore(
            "fibonacci", 50.0, f"sem grade: {ctx.estrutura.motivo_sem_fib or 'nenhum swing valido'}"
        )

    zona = fib.zona_do_preco(ctx.entry)
    if zona is None:
        return ComponenteScore("fibonacci", 45.0, "preco fora das zonas de retracao")

    base = {"nobre": 90.0, "rasa": 70.0, "profunda": 65.0, "alvos": 40.0}.get(zona.nome, 50.0)
    leitura = f"preco na zona {zona.nome} ({zona.descricao.split(' - ')[0]})"
    if fib.confluencias():
        base += 10
        leitura += "; ha nivel de fibonacci coincidindo com suporte/resistencia"
    return ComponenteScore("fibonacci", _clamp(base), leitura)


def nota_gatilho(ctx: ContextoScore) -> ComponenteScore:
    trigger = ctx.leitura.camada("trigger")
    if trigger is None:
        return ComponenteScore("gatilho", 0.0, "camada de gatilho indisponivel")
    if trigger.vies is not ctx.vies_alvo and trigger.vies is not Vies.NEUTRAL:
        return ComponenteScore("gatilho", 0.0, f"gatilho aponta para {trigger.vies.value}, contra a operacao")

    base = {
        TriggerState.BREAKOUT_WITH_VOLUME: 85.0,
        TriggerState.MA_RECLAIM: 70.0,
        TriggerState.REJECTION_WICK: 65.0,
        TriggerState.NONE: 0.0,
    }.get(trigger.estado, 0.0)
    nota = base + 15 * trigger.forca if base else 0.0
    leitura = trigger.razoes[0] if trigger.razoes else trigger.valor
    return ComponenteScore("gatilho", _clamp(nota), f"{trigger.valor}: {leitura}")


def nota_risco_retorno(ctx: ContextoScore) -> ComponenteScore:
    rr = ctx.rr
    if rr <= 0:
        return ComponenteScore("risco_retorno", 0.0, "stop e entrada no mesmo preco")
    nota = _escala(rr, 1.0, ctx.cfg.rr_bom)
    return ComponenteScore(
        "risco_retorno", _clamp(nota),
        f"risco/retorno de {rr:.2f} (risco {formata_dinheiro(ctx.risco_por_acao)} por acao)",
        detalhes={"rr": rr},
    )


AVALIADORES = {
    "tendencia": nota_tendencia,
    "estrutura": nota_estrutura,
    "volume": nota_volume,
    "vwap": nota_vwap,
    "medias": nota_medias,
    "momentum": nota_momentum,
    "volatilidade": nota_volatilidade,
    "suporte_resistencia": nota_suporte_resistencia,
    "fibonacci": nota_fibonacci,
    "gatilho": nota_gatilho,
    "risco_retorno": nota_risco_retorno,
}


def calcular(ctx: ContextoScore, pesos: PesosScore = PESOS_PADRAO) -> ScoreDetalhado:
    """Roda os onze componentes e monta o score detalhado."""
    componentes = []
    for chave, avaliador in AVALIADORES.items():
        peso = pesos.peso(chave)
        if peso <= 0:
            continue  # componente desligado pela configuracao
        base = avaliador(ctx)
        componentes.append(replace(base, peso=peso))
    return ScoreDetalhado(componentes=tuple(componentes), pesos=pesos)
