"""Relatorio de validacao e os alertas de degradacao fora da amostra.

O relatorio compara as tres particoes nas seis medidas pedidas e - mais
importante - diz quando o desempenho **cai fora da amostra**. Estrategia que
ganha no treino e perde na validacao nao esta com azar: esta ajustada demais
ao passado que ja conhecia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from ..backtest.models import BacktestResult
from .cofre import CofreDeTeste
from .divisao import DivisaoDeDados, Particao


class Severidade(str, Enum):
    CRITICO = "critico"
    ALERTA = "alerta"
    OBSERVACAO = "observacao"

    @property
    def simbolo(self) -> str:
        return {"critico": "✖", "alerta": "!", "observacao": "·"}[self.value]


@dataclass(frozen=True)
class Alerta:
    """Um sinal de degradacao, com o numero que o sustenta."""

    chave: str
    severidade: Severidade
    particao: Particao
    mensagem: str

    def para_dict(self) -> dict:
        return {
            "chave": self.chave, "severidade": self.severidade.value,
            "particao": self.particao.value, "mensagem": self.mensagem,
        }


@dataclass(frozen=True)
class Medidas:
    """As seis medidas de uma particao."""

    particao: Particao
    retorno_pct: float
    max_drawdown_pct: float
    profit_factor: Optional[float]
    sharpe: Optional[float]
    expectancy: float
    n_trades: int
    dias: int = 0

    @classmethod
    def de_resultado(cls, particao: Particao, resultado: BacktestResult,
                     dias: int = 0) -> "Medidas":
        m = resultado.metricas
        return cls(
            particao=particao,
            retorno_pct=m.retorno_total_pct,
            max_drawdown_pct=m.max_drawdown_pct,
            profit_factor=m.profit_factor,
            sharpe=m.sharpe,
            expectancy=m.expectancy,
            n_trades=m.n_trades,
            dias=dias or m.dias,
        )

    def para_dict(self) -> dict:
        def _r(v, casas=3):
            return None if v is None else round(v, casas)

        return {
            "particao": self.particao.value,
            "retorno_pct": _r(self.retorno_pct, 2),
            "max_drawdown_pct": _r(self.max_drawdown_pct, 2),
            "profit_factor": _r(self.profit_factor),
            "sharpe": _r(self.sharpe),
            "expectancy": _r(self.expectancy, 2),
            "n_trades": self.n_trades,
            "dias": self.dias,
        }


@dataclass(frozen=True)
class CriteriosDeDegradacao:
    """Quando a queda fora da amostra vira alerta."""

    queda_de_retorno_pct: float = 50.0  # % do retorno de treino que sumiu
    piora_de_drawdown: float = 1.8  # vezes o drawdown de treino
    profit_factor_minimo: float = 1.0
    queda_de_expectancy_pct: float = 50.0
    min_trades_para_concluir: int = 20


def c_min_trades(criterios: CriteriosDeDegradacao) -> int:
    return criterios.min_trades_para_concluir


class RelatorioDeValidacao:
    """Compara as particoes e aponta degradacao."""

    def __init__(
        self,
        divisao: DivisaoDeDados,
        medidas: Sequence[Medidas],
        cofre: Optional[CofreDeTeste] = None,
        criterios: Optional[CriteriosDeDegradacao] = None,
        selecao=None,
        candidato: str = "",
    ):
        self.divisao = divisao
        self.medidas = {m.particao: m for m in medidas}
        self.cofre = cofre
        self.criterios = criterios or CriteriosDeDegradacao()
        self.selecao = selecao
        self.candidato = candidato
        self.alertas: list[Alerta] = self._avaliar()

    # ------------------------------------------------------------------
    def medida(self, particao: Particao) -> Optional[Medidas]:
        return self.medidas.get(particao)

    @property
    def treino(self) -> Optional[Medidas]:
        return self.medidas.get(Particao.TRAIN)

    @property
    def criticos(self) -> list[Alerta]:
        return [a for a in self.alertas if a.severidade is Severidade.CRITICO]

    @property
    def degradou(self) -> bool:
        return bool(self.criticos)

    @property
    def veredito(self) -> str:
        if not self.treino:
            return "sem medida de treino para comparar"
        if self.treino.retorno_pct <= 0:
            return (
                f"o treino ja foi negativo ({self.treino.retorno_pct:+.2f}%): a estrategia "
                "nao funcionou nem no periodo em que foi ajustada"
            )
        if self.degradou:
            return (
                f"degradacao fora da amostra: {len(self.criticos)} sinal(is) critico(s) - "
                "os numeros do treino nao se sustentaram"
            )
        if self.alertas:
            return (
                f"desempenho se manteve fora da amostra, com {len(self.alertas)} ressalva(s)"
            )
        return "desempenho se manteve fora da amostra nas medidas comparadas"

    # ------------------------------------------------------------------
    def _avaliar(self) -> list[Alerta]:
        alertas: list[Alerta] = []
        treino = self.medidas.get(Particao.TRAIN)
        if treino is None:
            return alertas

        # validar o que ja falhou dentro da amostra nao faz sentido: sem
        # desempenho em treino nao ha o que "se sustentar" fora dele
        if treino.retorno_pct <= 0:
            alertas.append(Alerta(
                "treino_negativo", Severidade.CRITICO, Particao.TRAIN,
                f"o treino ja foi negativo ({treino.retorno_pct:+.2f}%): nao ha desempenho "
                "dentro da amostra para validar",
            ))
        if treino.n_trades < c_min_trades(self.criterios):
            alertas.append(Alerta(
                "treino_sem_amostra", Severidade.OBSERVACAO, Particao.TRAIN,
                f"{treino.n_trades} trades no treino: base fraca para qualquer comparacao",
            ))

        for particao in (Particao.VALIDATION, Particao.TEST):
            fora = self.medidas.get(particao)
            if fora is None:
                continue
            alertas.extend(self._comparar(treino, fora))

        if self.cofre is not None and self.cofre.contaminado:
            alertas.append(Alerta(
                "teste_contaminado", Severidade.CRITICO, Particao.TEST,
                f"o TEST foi aberto {self.cofre.vezes} vezes - a partir da segunda ele "
                "deixa de ser out-of-sample e o resultado final fica otimista",
            ))
        return alertas

    def _comparar(self, treino: Medidas, fora: Medidas) -> list[Alerta]:
        c = self.criterios
        p = fora.particao
        alertas: list[Alerta] = []

        if fora.n_trades < c.min_trades_para_concluir:
            alertas.append(Alerta(
                "amostra_pequena", Severidade.OBSERVACAO, p,
                f"{fora.n_trades} trades em {p.rotulo}: pouco para concluir qualquer coisa",
            ))

        if treino.retorno_pct > 0 and fora.retorno_pct <= 0:
            alertas.append(Alerta(
                "retorno_virou_negativo", Severidade.CRITICO, p,
                f"retorno de {treino.retorno_pct:+.2f}% no treino virou "
                f"{fora.retorno_pct:+.2f}% em {p.rotulo}",
            ))
        elif treino.retorno_pct > 0:
            queda = (1 - fora.retorno_pct / treino.retorno_pct) * 100
            if queda >= c.queda_de_retorno_pct:
                alertas.append(Alerta(
                    "retorno_caiu", Severidade.ALERTA, p,
                    f"retorno caiu {queda:.0f}% em {p.rotulo} "
                    f"({treino.retorno_pct:+.2f}% -> {fora.retorno_pct:+.2f}%)",
                ))

        if treino.max_drawdown_pct > 0:
            razao = fora.max_drawdown_pct / treino.max_drawdown_pct
            if razao >= c.piora_de_drawdown:
                alertas.append(Alerta(
                    "drawdown_piorou", Severidade.ALERTA, p,
                    f"drawdown {razao:.1f}x maior em {p.rotulo} "
                    f"({treino.max_drawdown_pct:.2f}% -> {fora.max_drawdown_pct:.2f}%)",
                ))

        if fora.profit_factor is not None and fora.profit_factor < c.profit_factor_minimo:
            alertas.append(Alerta(
                "profit_factor_abaixo_de_um", Severidade.CRITICO, p,
                f"profit factor de {fora.profit_factor:.2f} em {p.rotulo}: "
                "as perdas passaram os ganhos fora da amostra",
            ))

        if treino.expectancy > 0 and fora.expectancy <= 0:
            alertas.append(Alerta(
                "expectancy_virou_negativa", Severidade.CRITICO, p,
                f"expectancy virou negativa em {p.rotulo} "
                f"({treino.expectancy:+.2f} -> {fora.expectancy:+.2f})",
            ))
        elif treino.expectancy > 0 and fora.expectancy > 0:
            queda = (1 - fora.expectancy / treino.expectancy) * 100
            if queda >= c.queda_de_expectancy_pct:
                alertas.append(Alerta(
                    "expectancy_caiu", Severidade.ALERTA, p,
                    f"expectancy caiu {queda:.0f}% em {p.rotulo}",
                ))

        if (treino.sharpe is not None and fora.sharpe is not None
                and treino.sharpe > 0 and fora.sharpe <= 0):
            alertas.append(Alerta(
                "sharpe_virou_negativo", Severidade.ALERTA, p,
                f"Sharpe de {treino.sharpe:.2f} no treino virou {fora.sharpe:.2f} em {p.rotulo}",
            ))
        return alertas

    # ------------------------------------------------------------------
    def para_dict(self) -> dict:
        return {
            "candidato": self.candidato,
            "divisao": self.divisao.para_dict(),
            "medidas": [m.para_dict() for m in self.medidas.values()],
            "alertas": [a.para_dict() for a in self.alertas],
            "degradou": self.degradou,
            "veredito": self.veredito,
            "cofre": self.cofre.para_dict() if self.cofre else None,
            "selecao": self.selecao.para_dict() if self.selecao else None,
        }
