"""Comparar Timeframes: a mesma estrategia, os mesmos dados, varias escalas.

O que a funcionalidade responde: *em qual timeframe esta estrategia se
comporta melhor?* - e a resposta NAO e' "o que rendeu mais".

Um timeframe que rendeu 8% com 30% de drawdown e 4 trades nao e' melhor que
um que rendeu 3% com 5% de drawdown e 60 trades: o primeiro pode ser sorte,
o segundo tem cara de vantagem. Por isso a nota final combina retorno
ajustado ao risco, consistencia, tamanho da amostra e peso dos custos - e
qualquer timeframe pode ser reprovado, inclusive todos.

As escalas de nota sao ABSOLUTAS, nao relativas aos concorrentes: um
timeframe nao vira bom so por ser o menos ruim da lista.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Sequence, Union

from ...models import Series
from ..mtf.errors import MTFError
from ..mtf.timeframes import parse_timeframe, rotulo_canonico
from ..strategy.base import Strategy
from .config import BacktestConfig
from .engine import BacktestEngine
from .models import BacktestResult

TIMEFRAMES_PADRAO: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "1d")

FabricaEstrategia = Union[Strategy, Callable[[], Strategy]]


class StatusTimeframe(str, Enum):
    OK = "ok"
    SEM_TRADES = "sem trades"
    SEM_SINAIS = "sem sinais"
    NAO_APLICAVEL = "nao aplicavel"

    @property
    def rodou(self) -> bool:
        return self in (StatusTimeframe.OK, StatusTimeframe.SEM_TRADES)


@dataclass(frozen=True)
class CriteriosComparacao:
    """Como a nota e' formada. Tudo ajustavel, nada escondido no codigo."""

    pesos: dict = field(
        default_factory=lambda: {
            "retorno sobre drawdown": 0.25,
            "sharpe": 0.18,
            "profit factor": 0.18,
            "drawdown contido": 0.16,
            "expectancy (R)": 0.13,
            "peso dos custos": 0.10,
        }
    )
    # onde cada criterio atinge nota maxima
    romad_alvo: float = 3.0  # retorno / max drawdown
    sharpe_alvo: float = 2.0
    profit_factor_alvo: float = 2.0
    expectancy_alvo: float = 0.5  # em R por trade
    drawdown_tolerado_pct: float = 20.0  # nota zero a partir daqui
    trades_para_confianca: int = 30
    custos_confortaveis: float = 0.20  # ate 20% do lucro bruto: nota cheia
    custos_insustentaveis: float = 1.0  # custos comeram tudo: nota zero

    # reprovacao direta
    min_trades: int = 10
    drawdown_maximo_aceitavel_pct: float = 25.0

    def __post_init__(self) -> None:
        soma = sum(self.pesos.values())
        if abs(soma - 1.0) > 1e-6:
            raise ValueError(f"os pesos precisam somar 1,0 (somam {soma:.3f})")


PADRAO = CriteriosComparacao()


@dataclass(frozen=True)
class CriterioNota:
    nome: str
    valor: Optional[float]
    nota: float  # 0..1
    peso: float
    detalhe: str

    @property
    def contribuicao(self) -> float:
        return self.nota * self.peso


@dataclass
class LinhaComparacao:
    """Um timeframe na comparacao."""

    timeframe: str
    status: StatusTimeframe
    motivo: str = ""
    resultado: Optional[BacktestResult] = None
    notas: list[CriterioNota] = field(default_factory=list)
    score: float = 0.0  # 0..100, ja com o fator de confianca aplicado
    score_bruto: float = 0.0  # antes do desconto pela amostra
    confianca: float = 0.0  # 0..1
    elegivel: bool = False
    ressalvas: list[str] = field(default_factory=list)

    # -- atalhos para a tabela ------------------------------------------
    @property
    def retorno_pct(self) -> Optional[float]:
        return self.resultado.metricas.retorno_total_pct if self.resultado else None

    @property
    def retorno(self) -> Optional[float]:
        return self.resultado.metricas.retorno_total if self.resultado else None

    @property
    def max_drawdown_pct(self) -> Optional[float]:
        return self.resultado.metricas.max_drawdown_pct if self.resultado else None

    @property
    def profit_factor(self) -> Optional[float]:
        return self.resultado.metricas.profit_factor if self.resultado else None

    @property
    def sharpe(self) -> Optional[float]:
        return self.resultado.metricas.sharpe if self.resultado else None

    @property
    def win_rate(self) -> Optional[float]:
        return self.resultado.metricas.win_rate if self.resultado else None

    @property
    def n_trades(self) -> int:
        return self.resultado.metricas.n_trades if self.resultado else 0

    @property
    def custos(self) -> Optional[float]:
        return self.resultado.metricas.custos_totais if self.resultado else None

    @property
    def expectancy(self) -> Optional[float]:
        return self.resultado.metricas.expectancy if self.resultado else None

    @property
    def expectancy_em_r(self) -> Optional[float]:
        return self.resultado.metricas.expectancy_em_r if self.resultado else None

    def para_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "status": self.status.value,
            "motivo": self.motivo,
            "score": round(self.score, 1),
            "score_bruto": round(self.score_bruto, 1),
            "confianca_da_amostra": round(self.confianca, 3),
            "elegivel": self.elegivel,
            "ressalvas": list(self.ressalvas),
            "metricas": self.resultado.metricas.para_dict() if self.resultado else None,
            "notas": [
                {"nome": n.nome, "valor": n.valor, "nota": round(n.nota, 3),
                 "peso": n.peso, "detalhe": n.detalhe}
                for n in self.notas
            ],
        }


@dataclass
class ComparacaoTimeframes:
    """O resultado da comparacao inteira."""

    symbol: str
    estrategia: str
    capital_inicial: float
    linhas: list[LinhaComparacao]
    criterios: CriteriosComparacao = field(default_factory=CriteriosComparacao)
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    avisos: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def rodadas(self) -> list[LinhaComparacao]:
        return [l for l in self.linhas if l.status.rodou]

    @property
    def elegiveis(self) -> list[LinhaComparacao]:
        return [l for l in self.linhas if l.elegivel]

    @property
    def melhor_equilibrio(self) -> Optional[LinhaComparacao]:
        """Maior nota entre os aprovados - ``None`` quando nenhum passa."""
        if not self.elegiveis:
            return None
        return max(self.elegiveis, key=lambda l: l.score)

    @property
    def melhor_retorno(self) -> Optional[LinhaComparacao]:
        """Maior retorno, aprovado ou nao. Serve de contraponto, nao de escolha."""
        candidatos = [l for l in self.rodadas if l.retorno_pct is not None]
        if not candidatos:
            return None
        return max(candidatos, key=lambda l: l.retorno_pct)

    @property
    def divergem(self) -> bool:
        """O maior retorno nao e' o melhor equilibrio - o caso mais instrutivo."""
        melhor, retorno = self.melhor_equilibrio, self.melhor_retorno
        return bool(melhor and retorno and melhor.timeframe != retorno.timeframe)

    @property
    def veredito(self) -> str:
        melhor = self.melhor_equilibrio
        if melhor is None:
            rodaram = len(self.rodadas)
            if not rodaram:
                return "nenhum timeframe pode ser avaliado com estes dados"
            return (
                "nenhum timeframe passou nos criterios minimos de risco e amostra - "
                "a estrategia nao se sustenta em nenhuma das escalas testadas"
            )
        texto = f"{melhor.timeframe} e' o timeframe mais equilibrado (nota {melhor.score:.0f}/100)"
        if self.divergem:
            outro = self.melhor_retorno
            texto += (
                f"; o maior retorno foi de {outro.timeframe} "
                f"({outro.retorno_pct:+.2f}% com {outro.max_drawdown_pct:.2f}% de drawdown "
                f"e {outro.n_trades} trades), que nao compensa o risco"
            )
        if melhor.ressalvas:
            texto += f". Ressalvas: {'; '.join(melhor.ressalvas)}"
        return texto

    def para_dict(self) -> dict:
        melhor = self.melhor_equilibrio
        retorno = self.melhor_retorno
        return {
            "symbol": self.symbol,
            "estrategia": self.estrategia,
            "capital_inicial": round(self.capital_inicial, 2),
            "inicio": self.inicio.isoformat() if self.inicio else None,
            "fim": self.fim.isoformat() if self.fim else None,
            "melhor_equilibrio": melhor.timeframe if melhor else None,
            "melhor_retorno": retorno.timeframe if retorno else None,
            "divergem": self.divergem,
            "veredito": self.veredito,
            "pesos": dict(self.criterios.pesos),
            "linhas": [l.para_dict() for l in self.linhas],
            "avisos": list(self.avisos),
        }


# ---------------------------------------------------------------------------
# notas
# ---------------------------------------------------------------------------


def escala(valor: Optional[float], zero: float, um: float) -> float:
    """Converte uma leitura em nota 0..1 com escala ABSOLUTA."""
    if valor is None:
        return 0.0
    if um == zero:
        return 0.0
    return max(0.0, min(1.0, (valor - zero) / (um - zero)))


def avaliar(resultado: BacktestResult, criterios: CriteriosComparacao = PADRAO) -> list[CriterioNota]:
    """Nota de cada criterio para um resultado de backtest."""
    m = resultado.metricas
    p = criterios.pesos

    romad = (m.retorno_total / m.max_drawdown) if m.max_drawdown > 0 else (
        criterios.romad_alvo if m.retorno_total > 0 else 0.0
    )
    lucro_bruto = m.retorno_total + m.custos_totais
    fracao_custos = (m.custos_totais / lucro_bruto) if lucro_bruto > 0 else 1.0

    return [
        CriterioNota(
            "retorno sobre drawdown", romad,
            escala(romad, 0.0, criterios.romad_alvo), p["retorno sobre drawdown"],
            f"{romad:.2f}x o drawdown maximo (alvo {criterios.romad_alvo:.1f}x)",
        ),
        CriterioNota(
            "sharpe", m.sharpe,
            escala(m.sharpe, 0.0, criterios.sharpe_alvo), p["sharpe"],
            "sem dados suficientes" if m.sharpe is None else f"{m.sharpe:.2f} (alvo {criterios.sharpe_alvo:.1f})",
        ),
        CriterioNota(
            "profit factor", m.profit_factor,
            escala(m.profit_factor, 1.0, criterios.profit_factor_alvo), p["profit factor"],
            "sem perdas para comparar" if m.profit_factor is None
            else f"{m.profit_factor:.2f} (alvo {criterios.profit_factor_alvo:.1f})",
        ),
        CriterioNota(
            "drawdown contido", m.max_drawdown_pct,
            1.0 - escala(m.max_drawdown_pct, 0.0, criterios.drawdown_tolerado_pct),
            p["drawdown contido"],
            f"{m.max_drawdown_pct:.2f}% (tolerado ate {criterios.drawdown_tolerado_pct:.0f}%)",
        ),
        CriterioNota(
            "expectancy (R)", m.expectancy_em_r,
            escala(m.expectancy_em_r, 0.0, criterios.expectancy_alvo), p["expectancy (R)"],
            f"{m.expectancy_em_r:+.3f} R por trade (alvo {criterios.expectancy_alvo:.2f})",
        ),
        CriterioNota(
            "peso dos custos", fracao_custos,
            1.0 - escala(fracao_custos, criterios.custos_confortaveis, criterios.custos_insustentaveis),
            p["peso dos custos"],
            f"custos consumiram {fracao_custos * 100:.0f}% do lucro bruto"
            if lucro_bruto > 0 else "sem lucro bruto para cobrir os custos",
        ),
    ]


def elegibilidade(resultado: BacktestResult, criterios: CriteriosComparacao = PADRAO) -> tuple[bool, list[str]]:
    """Um timeframe so e' recomendavel se passar nestes cortes duros."""
    m = resultado.metricas
    ressalvas: list[str] = []
    reprovado: list[str] = []

    if m.retorno_total <= 0:
        reprovado.append("retorno nao positivo")
    if m.n_trades < criterios.min_trades:
        reprovado.append(f"amostra insuficiente ({m.n_trades} trades)")
    if m.max_drawdown_pct > criterios.drawdown_maximo_aceitavel_pct:
        reprovado.append(f"drawdown de {m.max_drawdown_pct:.1f}% acima do aceitavel")
    if m.profit_factor is not None and m.profit_factor < 1.0:
        reprovado.append(f"profit factor de {m.profit_factor:.2f} abaixo de 1")

    if m.n_trades < criterios.trades_para_confianca and not reprovado:
        ressalvas.append(f"apenas {m.n_trades} trades: amostra ainda pequena")
    if resultado.metricas.dias < 20 and not reprovado:
        ressalvas.append(f"apenas {resultado.metricas.dias} pregoes no periodo")

    return (not reprovado), (reprovado + ressalvas)


def fator_confianca(n_trades: int, criterios: CriteriosComparacao = PADRAO) -> float:
    """Quanto da nota a amostra sustenta (0..1).

    Tamanho de amostra nao torna uma estrategia boa - torna a estimativa
    confiavel. Por isso ele nao entra como mais um criterio somado aos outros:
    ele multiplica a nota inteira. Um timeframe com um unico trade vencedor
    tem drawdown zero e expectancy otima, e a nota crua o colocaria em
    primeiro; o fator derruba isso para o que ele e' - uma amostra de um.

    A raiz vem do erro padrao, que encolhe com a raiz do numero de amostras.
    """
    if n_trades <= 0:
        return 0.0
    alvo = max(criterios.trades_para_confianca, 1)
    return min(1.0, (n_trades / alvo) ** 0.5)


def pontuar(notas: Sequence[CriterioNota], n_trades: int = 0,
            criterios: CriteriosComparacao = PADRAO) -> float:
    """Nota final 0..100, ja descontada a confianca da amostra."""
    bruta = sum(n.contribuicao for n in notas)
    return round(bruta * fator_confianca(n_trades, criterios) * 100.0, 1)


# ---------------------------------------------------------------------------
# execucao
# ---------------------------------------------------------------------------


def comparar(
    estrategia: FabricaEstrategia,
    serie_base: Series,
    config: Optional[BacktestConfig] = None,
    timeframes: Sequence[str] = TIMEFRAMES_PADRAO,
    criterios: CriteriosComparacao = PADRAO,
) -> ComparacaoTimeframes:
    """Roda o mesmo backtest em cada timeframe e compara.

    Muda apenas o timeframe em que a estrategia decide - dados, capital,
    custos, horario e limites de risco sao identicos em todas as rodadas, que
    e' o que torna a comparacao justa.
    """
    config = config or BacktestConfig()
    symbol = config.symbol or serie_base.symbol
    base = parse_timeframe(config.timeframe_base)
    linhas: list[LinhaComparacao] = []
    avisos: list[str] = []
    inicio = fim = None
    nome_estrategia = ""

    for bruto in timeframes:
        rotulo = rotulo_canonico(bruto)
        tf = parse_timeframe(rotulo)

        if not tf.eh_multiplo_de(base):
            linhas.append(
                LinhaComparacao(
                    timeframe=rotulo,
                    status=StatusTimeframe.NAO_APLICAVEL,
                    motivo=f"{rotulo} nao e' multiplo do timeframe de execucao ({base.rotulo})",
                )
            )
            continue

        instancia = estrategia() if callable(estrategia) else estrategia
        nome_estrategia = nome_estrategia or instancia.nome
        rodada = replace(config, symbol=symbol, timeframe_setup=rotulo)

        try:
            resultado = BacktestEngine(instancia, rodada).rodar(serie_base)
        except MTFError as e:
            # uma escala impossivel nao pode derrubar a comparacao inteira:
            # ela sai da lista com o motivo, e as outras seguem
            linhas.append(
                LinhaComparacao(rotulo, StatusTimeframe.NAO_APLICAVEL, motivo=str(e))
            )
            continue

        inicio = inicio or resultado.inicio
        fim = resultado.fim or fim

        if resultado.sinais_avaliados == 0:
            linhas.append(
                LinhaComparacao(
                    timeframe=rotulo,
                    status=StatusTimeframe.SEM_SINAIS,
                    motivo="nenhum candle fechado suficiente para a estrategia avaliar",
                    resultado=resultado,
                )
            )
            continue

        notas = avaliar(resultado, criterios)
        elegivel, ressalvas = elegibilidade(resultado, criterios)
        status = StatusTimeframe.OK if resultado.metricas.n_trades else StatusTimeframe.SEM_TRADES
        if status is StatusTimeframe.SEM_TRADES:
            elegivel = False
            ressalvas = ["nenhum trade executado"] + ressalvas

        linhas.append(
            LinhaComparacao(
                timeframe=rotulo,
                status=status,
                motivo="" if status is StatusTimeframe.OK else "a estrategia avaliou, mas nao acionou",
                resultado=resultado,
                notas=notas,
                score=pontuar(notas, resultado.metricas.n_trades, criterios),
                score_bruto=round(sum(n.contribuicao for n in notas) * 100.0, 1),
                confianca=fator_confianca(resultado.metricas.n_trades, criterios),
                elegivel=elegivel,
                ressalvas=ressalvas,
            )
        )

    if not any(l.status.rodou for l in linhas):
        avisos.append("nenhum timeframe produziu uma rodada avaliavel com estes dados")

    return ComparacaoTimeframes(
        symbol=symbol,
        estrategia=nome_estrategia,
        capital_inicial=config.capital_inicial,
        linhas=linhas,
        criterios=criterios,
        inicio=inicio,
        fim=fim,
        avisos=avisos,
    )
