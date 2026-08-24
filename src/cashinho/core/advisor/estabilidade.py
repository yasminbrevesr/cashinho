"""Histerese: a recomendacao nao pode oscilar a cada atualizacao.

Trocar 5m -> 2m -> 5m -> 3m em quinze minutos e' pior do que ficar num
timeframe mediano: nenhum setup chega a maturar, e o operador perde a
referencia. Duas travas, as duas configuraveis:

    VANTAGEM MINIMA   o novo precisa ser MELHOR POR UMA MARGEM, nao so melhor
    TEMPO MINIMO      a recomendacao atual tem um prazo de carencia

A margem cai quando o timeframe atual esta claramente ruim: 5m em 63 contra
2m em 88 e' motivo para trocar; 82 contra 84 nao e'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass(frozen=True)
class ConfigEstabilidade:
    """As travas da troca de recomendacao."""

    vantagem_minima: float = 8.0          # pontos de score
    tempo_minimo_min: float = 15.0        # minutos de carencia
    score_ruim: float = 55.0              # abaixo disso, a carencia cai
    vantagem_minima_se_ruim: float = 4.0

    def para_dict(self) -> dict:
        return {"vantagem_minima": self.vantagem_minima,
                "tempo_minimo_min": self.tempo_minimo_min,
                "score_ruim": self.score_ruim,
                "vantagem_minima_se_ruim": self.vantagem_minima_se_ruim}


@dataclass(frozen=True)
class RecomendacaoAtual:
    """O que ja estava recomendado - a memoria entre uma analise e a proxima."""

    timeframe: str
    desde: datetime
    score: float

    def idade_min(self, agora: datetime) -> float:
        return (agora - self.desde).total_seconds() / 60


@dataclass(frozen=True)
class Decisao:
    """Trocar ou manter - com a conta que levou a isso."""

    manter: bool
    timeframe: str
    motivo: str
    vantagem: float = 0.0

    def para_dict(self) -> dict:
        return {"manter": self.manter, "timeframe": self.timeframe,
                "motivo": self.motivo, "vantagem": round(self.vantagem, 1)}


def decidir(candidato: str, score_candidato: float,
            atual: Optional[RecomendacaoAtual], agora: datetime,
            config: Optional[ConfigEstabilidade] = None,
            score_do_atual: Optional[float] = None) -> Decisao:
    """A troca vale a pena, ou e' so ruido de pontuacao?"""
    cfg = config or ConfigEstabilidade()

    if atual is None:
        return Decisao(False, candidato, "primeira recomendacao para este ativo")
    if candidato == atual.timeframe:
        return Decisao(True, atual.timeframe, "o melhor continua sendo o atual")

    referencia = score_do_atual if score_do_atual is not None else atual.score
    vantagem = score_candidato - referencia

    atual_esta_ruim = referencia < cfg.score_ruim
    minima = cfg.vantagem_minima_se_ruim if atual_esta_ruim else cfg.vantagem_minima

    if vantagem < minima:
        return Decisao(
            True, atual.timeframe,
            f"{candidato} esta {vantagem:+.1f} ponto(s) a frente de "
            f"{atual.timeframe} - abaixo da margem de {minima:.0f} para trocar",
            vantagem)

    idade = atual.idade_min(agora)
    if idade < cfg.tempo_minimo_min and not atual_esta_ruim:
        return Decisao(
            True, atual.timeframe,
            f"{atual.timeframe} recomendado ha {idade:.0f} min - a carencia e' de "
            f"{cfg.tempo_minimo_min:.0f} min", vantagem)

    razao = (f"{atual.timeframe} caiu para {referencia:.0f}" if atual_esta_ruim
             else f"vantagem de {vantagem:+.1f} pontos")
    return Decisao(False, candidato,
                   f"troca de {atual.timeframe} para {candidato}: {razao}", vantagem)
