"""Estatisticas do diario - aritmetica, nada alem disso.

**Nao ha IA aqui, e nao deve haver nesta etapa.** Nenhuma funcao deste modulo
sugere mudanca de estrategia, ajusta peso ou "aprende" coisa alguma. Ela conta
trades, soma resultados e divide - operacoes que qualquer pessoa refaz na mao
e chega no mesmo numero.

A leitura do que fazer com esses numeros e' sua. O diario mede; quem decide
e' voce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from .modelos import DIAS_DA_SEMANA, Registro

AMOSTRA_MINIMA = 20
"""Abaixo disso, os numeros dizem pouco - e a tela avisa."""


@dataclass(frozen=True)
class Estatistica:
    """O desempenho de um grupo de operacoes."""

    grupo: str
    n_trades: int = 0
    vencedores: int = 0
    perdedores: int = 0
    zerados: int = 0
    resultado_total: float = 0.0
    resultado_medio: float = 0.0
    ganho_medio: float = 0.0
    perda_media: float = 0.0
    melhor: float = 0.0
    pior: float = 0.0
    custos: float = 0.0
    r_medio: float = 0.0
    duracao_media_min: float = 0.0
    payoff: Optional[float] = None
    profit_factor: Optional[float] = None

    @property
    def win_rate(self) -> float:
        return self.vencedores / self.n_trades if self.n_trades else 0.0

    @property
    def loss_rate(self) -> float:
        return self.perdedores / self.n_trades if self.n_trades else 0.0

    @property
    def expectancy(self) -> float:
        """Resultado esperado por trade, em reais."""
        return self.win_rate * self.ganho_medio - self.loss_rate * self.perda_media

    @property
    def amostra_pequena(self) -> bool:
        return self.n_trades < AMOSTRA_MINIMA

    def para_dict(self) -> dict:
        def _r(v, casas=2):
            return None if v is None else round(v, casas)

        return {
            "grupo": self.grupo,
            "n_trades": self.n_trades,
            "vencedores": self.vencedores,
            "perdedores": self.perdedores,
            "win_rate": _r(self.win_rate, 4),
            "resultado_total": _r(self.resultado_total),
            "resultado_medio": _r(self.resultado_medio),
            "ganho_medio": _r(self.ganho_medio),
            "perda_media": _r(self.perda_media),
            "payoff": _r(self.payoff, 3),
            "profit_factor": _r(self.profit_factor, 3),
            "expectancy": _r(self.expectancy),
            "r_medio": _r(self.r_medio, 3),
            "melhor": _r(self.melhor),
            "pior": _r(self.pior),
            "custos": _r(self.custos),
            "duracao_media_min": _r(self.duracao_media_min, 1),
            "amostra_pequena": self.amostra_pequena,
        }


def calcular(registros: Sequence[Registro], grupo: str = "todos") -> Estatistica:
    """Soma, conta e divide. Sem nenhum ajuste escondido."""
    if not registros:
        return Estatistica(grupo=grupo)

    resultados = [r.resultado for r in registros]
    ganhos = [v for v in resultados if v > 0]
    perdas = [-v for v in resultados if v < 0]
    n = len(registros)

    ganho_medio = sum(ganhos) / len(ganhos) if ganhos else 0.0
    perda_media = sum(perdas) / len(perdas) if perdas else 0.0

    return Estatistica(
        grupo=grupo,
        n_trades=n,
        vencedores=len(ganhos),
        perdedores=len(perdas),
        zerados=n - len(ganhos) - len(perdas),
        resultado_total=sum(resultados),
        resultado_medio=sum(resultados) / n,
        ganho_medio=ganho_medio,
        perda_media=perda_media,
        melhor=max(resultados),
        pior=min(resultados),
        custos=sum(r.custos for r in registros),
        r_medio=sum(r.resultado_em_r for r in registros) / n,
        duracao_media_min=sum(r.duracao_minutos for r in registros) / n,
        # None quando nao ha perdas: a razao seria infinita, e inventar um
        # numero aqui daria a impressao de desempenho perfeito
        payoff=(ganho_medio / perda_media) if perda_media else None,
        profit_factor=(sum(ganhos) / sum(perdas)) if perdas else None,
    )


# ---------------------------------------------------------------------------
# agrupamentos
# ---------------------------------------------------------------------------


def agrupar(
    registros: Sequence[Registro],
    chave: Callable[[Registro], str],
    ordenar_por: str = "resultado",
) -> list[Estatistica]:
    """Agrupa por uma chave qualquer e calcula a estatistica de cada grupo."""
    grupos: dict[str, list[Registro]] = {}
    for r in registros:
        grupos.setdefault(chave(r), []).append(r)

    estatisticas = [calcular(rs, grupo) for grupo, rs in grupos.items()]
    ordens = {
        "resultado": lambda e: (-e.resultado_total, e.grupo),
        "trades": lambda e: (-e.n_trades, e.grupo),
        "win_rate": lambda e: (-e.win_rate, e.grupo),
        "expectancy": lambda e: (-e.expectancy, e.grupo),
        "grupo": lambda e: (e.grupo,),
    }
    estatisticas.sort(key=ordens.get(ordenar_por, ordens["resultado"]))
    return estatisticas


def por_setup(registros: Sequence[Registro], **kwargs) -> list[Estatistica]:
    return agrupar(registros, lambda r: r.setup or "(sem setup)", **kwargs)


def por_ativo(registros: Sequence[Registro], **kwargs) -> list[Estatistica]:
    return agrupar(registros, lambda r: r.symbol, **kwargs)


def por_horario(registros: Sequence[Registro], **kwargs) -> list[Estatistica]:
    """Agrupa pela hora da ENTRADA - e' quando a decisao foi tomada."""
    kwargs.setdefault("ordenar_por", "grupo")
    return agrupar(registros, lambda r: f"{r.hora:02d}h", **kwargs)


def por_dia_da_semana(registros: Sequence[Registro], **kwargs) -> list[Estatistica]:
    kwargs.setdefault("ordenar_por", "grupo")
    estatisticas = agrupar(registros, lambda r: r.dia_da_semana, **kwargs)
    ordem = {d: i for i, d in enumerate(DIAS_DA_SEMANA)}
    if kwargs.get("ordenar_por") == "grupo":
        estatisticas.sort(key=lambda e: ordem.get(e.grupo, 99))
    return estatisticas


def por_timeframe(registros: Sequence[Registro], **kwargs) -> list[Estatistica]:
    return agrupar(registros, lambda r: r.timeframe_setup or "(sem timeframe)", **kwargs)


AGRUPAMENTOS = {
    "setup": por_setup,
    "ativo": por_ativo,
    "horario": por_horario,
    "dia": por_dia_da_semana,
    "timeframe": por_timeframe,
}


def todos_os_agrupamentos(registros: Sequence[Registro]) -> dict[str, list[Estatistica]]:
    return {nome: f(registros) for nome, f in AGRUPAMENTOS.items()}
