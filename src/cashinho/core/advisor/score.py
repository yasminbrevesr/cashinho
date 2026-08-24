"""O score do Advisor - seis componentes, nenhum deles caixa-preta.

Duas coisas ficam **separadas de proposito**, e essa e' a decisao central do
modulo:

    MARKET FIT           o comportamento de agora favorece este timeframe?
    STATISTICAL EVIDENCE ha historico suficiente para sustentar isso?

Uma manha boa de negociacao produz market fit alto e evidencia baixa. Juntar
os dois num numero so transformaria sorte recente em conclusao - que e'
exatamente o erro que este componente existe para nao cometer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Mapping, Optional

from ..structure.models import Regime
from .medidas import MedidasDoTimeframe


class PesosInvalidosError(ValueError):
    """Combinacao de pesos impossivel de usar."""


@dataclass(frozen=True)
class PesosAdvisor:
    """Quanto cada componente vale. Configuravel, normalizado pela soma."""

    regime: float = 0.25
    estrutura: float = 0.20
    ruido: float = 0.15
    liquidez: float = 0.15
    performance: float = 0.15
    estabilidade: float = 0.10

    def __post_init__(self) -> None:
        for nome, valor in asdict(self).items():
            if valor < 0:
                raise PesosInvalidosError(f"peso de {nome} nao pode ser negativo")
        if self.soma <= 0:
            raise PesosInvalidosError("ao menos um componente precisa ter peso")

    @property
    def soma(self) -> float:
        return sum(asdict(self).values())

    def normalizados(self) -> dict[str, float]:
        soma = self.soma
        return {k: v / soma for k, v in asdict(self).items()}

    def atualizar(self, **campos: float) -> "PesosAdvisor":
        desconhecidos = set(campos) - set(asdict(self))
        if desconhecidos:
            raise PesosInvalidosError(
                f"componentes desconhecidos: {', '.join(sorted(desconhecidos))}")
        return replace(self, **campos)

    def para_dict(self) -> dict:
        return asdict(self)


PESOS_PADRAO = PesosAdvisor()

NOMES = {
    "regime": "Regime", "estrutura": "Estrutura", "ruido": "Ruido",
    "liquidez": "Liquidez", "performance": "Performance",
    "estabilidade": "Estabilidade",
}


@dataclass(frozen=True)
class Componente:
    """A nota de um componente e a frase que a justifica."""

    chave: str
    nota: Optional[float]        # 0..100, ou None quando indisponivel
    leitura: str
    peso: float = 1.0

    @property
    def nome(self) -> str:
        return NOMES.get(self.chave, self.chave)

    @property
    def disponivel(self) -> bool:
        return self.nota is not None

    def para_dict(self) -> dict:
        return {"chave": self.chave, "nome": self.nome,
                "nota": None if self.nota is None else round(self.nota, 1),
                "peso": self.peso, "leitura": self.leitura,
                "disponivel": self.disponivel}


@dataclass(frozen=True)
class ScoreDoTimeframe:
    """As notas de um timeframe, com os dois totais separados."""

    timeframe: str
    componentes: tuple[Componente, ...]
    pesos: PesosAdvisor = PESOS_PADRAO

    # -- os dois numeros que nao se misturam --------------------------
    @property
    def market_fit(self) -> float:
        """Adequacao ao mercado de agora - sem nenhuma estatistica dentro."""
        return self._media(("regime", "estrutura", "ruido", "liquidez", "estabilidade"))

    @property
    def statistical_evidence(self) -> Optional[float]:
        """Evidencia estatistica. ``None`` quando nao ha historico."""
        componente = self.componente("performance")
        return componente.nota if componente and componente.disponivel else None

    @property
    def total(self) -> float:
        """A media ponderada de tudo o que estava disponivel."""
        return self._media(tuple(NOMES))

    # ------------------------------------------------------------------
    def componente(self, chave: str) -> Optional[Componente]:
        for c in self.componentes:
            if c.chave == chave:
                return c
        return None

    @property
    def indisponiveis(self) -> tuple[str, ...]:
        return tuple(c.nome for c in self.componentes if not c.disponivel)

    def piores(self, quantos: int = 2) -> list[Componente]:
        disponiveis = [c for c in self.componentes if c.disponivel]
        return sorted(disponiveis, key=lambda c: c.nota)[:quantos]

    def melhores(self, quantos: int = 2) -> list[Componente]:
        disponiveis = [c for c in self.componentes if c.disponivel]
        return sorted(disponiveis, key=lambda c: -c.nota)[:quantos]

    def _media(self, chaves: tuple[str, ...]) -> float:
        soma_pesos = 0.0
        soma = 0.0
        for c in self.componentes:
            if c.chave not in chaves or not c.disponivel:
                continue
            soma += c.nota * c.peso
            soma_pesos += c.peso
        return round(soma / soma_pesos, 1) if soma_pesos > 0 else 0.0

    def para_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "total": self.total,
            "market_fit": self.market_fit,
            "statistical_evidence": self.statistical_evidence,
            "componentes": [c.para_dict() for c in self.componentes],
            "indisponiveis": list(self.indisponiveis),
        }


# ---------------------------------------------------------------------------
# calculo
# ---------------------------------------------------------------------------


def _nota_de_regime(medidas: MedidasDoTimeframe, regime_do_contexto) -> Componente:
    """Timeframe alinhado com o regime que o contexto mostra vale mais."""
    peso = PESOS_PADRAO.regime
    if medidas.regime is None:
        return Componente("regime", None, "estrutura indisponivel neste timeframe", peso)

    tendencia = medidas.regime in (Regime.ALTA, Regime.BAIXA)
    if regime_do_contexto is None:
        nota = 70.0 if tendencia else 45.0
        return Componente("regime", nota,
                          f"{medidas.regime.value} (sem contexto para comparar)", peso)

    if medidas.regime is regime_do_contexto:
        # tendencia forte alinhada com o contexto vale mais que tendencia fraca
        forca = medidas.forca_da_tendencia
        nota = 92.0 if forca is None else round(70 + 25 * min(forca, 1.0), 1)
        detalhe = "" if forca is None else f", forca {forca:.0%}"
        return Componente("regime", nota,
                          f"{medidas.regime.value}, igual ao contexto{detalhe}", peso)
    contexto_lateral = regime_do_contexto is Regime.LATERAL
    if contexto_lateral and tendencia:
        return Componente("regime", 55.0,
                          f"{medidas.regime.value} dentro de contexto lateral", peso)
    if tendencia:
        return Componente("regime", 30.0,
                          f"{medidas.regime.value} CONTRA o contexto "
                          f"({regime_do_contexto.value})", peso)
    return Componente("regime", 50.0,
                      f"{medidas.regime.value} sob contexto {regime_do_contexto.value}",
                      peso)


# densidade de pivos por candle: abaixo da faixa nao ha estrutura para ler,
# acima dela cada oscilacao vira "pivo" e o desenho perde sentido
DENSIDADE_IDEAL = (0.04, 0.14)


def _nota_de_estrutura(medidas: MedidasDoTimeframe) -> Componente:
    """Estrutura legivel: **densidade** de pivos, nao contagem.

    Contar pivos premiava justamente o timeframe mais ruidoso - o 1m tem
    muito mais pivos que o 15m, e isso nao o torna melhor de operar. O que
    importa e' haver pivo suficiente para desenhar a operacao sem que cada
    balanco vire um.
    """
    peso = PESOS_PADRAO.estrutura
    if medidas.pivos == 0:
        return Componente("estrutura", None, "nenhum pivo confirmado ainda", peso)
    if medidas.candles <= 0:
        return Componente("estrutura", None, "sem candles para medir densidade", peso)

    densidade = medidas.pivos / medidas.candles
    baixa, alta = DENSIDADE_IDEAL
    if densidade < baixa:
        base = max(0.0, densidade / baixa) * 100
        forma = f"{medidas.pivos} pivo(s) em {medidas.candles} candles: estrutura rala"
    elif densidade > alta:
        # excesso derruba proporcionalmente ao quanto passou da faixa
        base = max(0.0, 1.0 - (densidade - alta) / alta) * 100
        forma = (f"{medidas.pivos} pivo(s) em {medidas.candles} candles: "
                 f"cada balanco vira pivo")
    else:
        base = 100.0
        forma = f"{medidas.pivos} pivo(s) em {medidas.candles} candles"

    taxa = medidas.taxa_de_falso_rompimento
    if taxa is None:
        return Componente("estrutura", round(base * 0.85, 1),
                          f"{forma}, sem rompimento para avaliar", peso)

    nota = base * (1.0 - taxa * 0.8)
    return Componente("estrutura", round(max(nota, 0.0), 1),
                      f"{forma}, {taxa:.0%} dos rompimentos foram falsos", peso)


def _nota_de_ruido(medidas: MedidasDoTimeframe) -> Componente:
    peso = PESOS_PADRAO.ruido
    m = medidas.eficiencia
    if not m.disponivel:
        return Componente("ruido", None, m.leitura, peso)
    # eficiencia de 0.5 ja e' bem direcional; acima disso satura
    nota = min(m.valor / 0.5, 1.0) * 100
    return Componente("ruido", round(nota, 1), m.leitura, peso)


def _nota_de_liquidez(medidas: MedidasDoTimeframe) -> Componente:
    """Volume da janela e, quando ha book, o quanto o spread custa."""
    peso = PESOS_PADRAO.liquidez
    volume, spread = medidas.volume_relativo, medidas.spread_relativo

    if not volume.disponivel and not spread.disponivel:
        return Componente("liquidez", None,
                          "sem volume nem spread para avaliar custo", peso)

    partes, leituras = [], []
    if volume.disponivel:
        partes.append(min(volume.valor / 1.2, 1.0) * 100)
        leituras.append(volume.leitura)
    if spread.disponivel:
        # 5% da amplitude ainda e' bom; 20% inviabiliza o timeframe
        partes.append(max(0.0, 1.0 - spread.valor / 0.20) * 100)
        leituras.append(spread.leitura)
    else:
        leituras.append("spread indisponivel nesta fonte")

    return Componente("liquidez", round(sum(partes) / len(partes), 1),
                      "; ".join(leituras), peso)


def _nota_de_performance(estatistica) -> Componente:
    """So existe com historico. Sem ele, **indisponivel** - nunca inventado."""
    peso = PESOS_PADRAO.performance
    if estatistica is None or not estatistica.disponivel:
        return Componente("performance", None,
                          "sem historico comparavel para este timeframe", peso)
    return Componente("performance", estatistica.nota, estatistica.leitura, peso)


def _nota_de_estabilidade(medidas: MedidasDoTimeframe) -> Componente:
    peso = PESOS_PADRAO.estabilidade
    m = medidas.estabilidade
    if not m.disponivel:
        return Componente("estabilidade", None, m.leitura, peso)
    return Componente("estabilidade", round(m.valor * 100, 1), m.leitura, peso)


def calcular(medidas: MedidasDoTimeframe, regime_do_contexto=None,
             estatistica=None, pesos: Optional[PesosAdvisor] = None) -> ScoreDoTimeframe:
    """As seis notas de um timeframe."""
    pesos = pesos or PESOS_PADRAO
    normalizados = pesos.normalizados()

    componentes = (
        _nota_de_regime(medidas, regime_do_contexto),
        _nota_de_estrutura(medidas),
        _nota_de_ruido(medidas),
        _nota_de_liquidez(medidas),
        _nota_de_performance(estatistica),
        _nota_de_estabilidade(medidas),
    )
    # o peso configurado entra aqui, sobre a nota ja calculada
    componentes = tuple(
        Componente(c.chave, c.nota, c.leitura, normalizados.get(c.chave, c.peso))
        for c in componentes
    )
    return ScoreDoTimeframe(medidas.timeframe, componentes, pesos)
