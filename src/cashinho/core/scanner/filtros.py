"""Filtros iniciais: descartar barato antes de analisar caro.

Rodar o pipeline inteiro em vinte ativos custa tempo. Estes filtros olham
apenas a serie bruta e eliminam o que nem deveria entrar na fila: papel sem
liquidez, ativo parado hoje, serie incompleta, volatilidade fora do operavel
e spread largo demais.

Como no auditor, ha tres respostas - passou, nao passou e **nao verificado**.
Spread so e' checado quando alguem informa: sem book, o scanner diz que nao
checou, em vez de fingir que esta tudo bem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...indicators.volatility import atr_percentual
from ...models import BRT, Series, formata_dinheiro


@dataclass(frozen=True)
class Filtro:
    """Resultado de um filtro para um ativo."""

    chave: str
    titulo: str
    passou: bool
    detalhe: str
    verificado: bool = True
    valor: Optional[float] = None

    @property
    def simbolo(self) -> str:
        if not self.verificado:
            return "?"
        return "✔" if self.passou else "✖"

    def para_dict(self) -> dict:
        return {
            "chave": self.chave, "titulo": self.titulo, "passou": self.passou,
            "verificado": self.verificado, "detalhe": self.detalhe,
            "valor": round(self.valor, 4) if self.valor is not None else None,
        }


def _ok(chave, titulo, detalhe, valor=None) -> Filtro:
    return Filtro(chave, titulo, True, detalhe, valor=valor)


def _corta(chave, titulo, detalhe, valor=None) -> Filtro:
    return Filtro(chave, titulo, False, detalhe, valor=valor)


def _nao_checado(chave, titulo, motivo) -> Filtro:
    return Filtro(chave, titulo, True, motivo, verificado=False)


# ---------------------------------------------------------------------------


def dados_disponiveis(serie: Series, cfg, agora: Optional[datetime] = None) -> Filtro:
    """Serie longa o bastante e recente o bastante para valer analise."""
    titulo = "dados disponiveis"
    if len(serie) < cfg.candles_minimos:
        return _corta("dados", titulo,
                      f"{len(serie)} candles, minimo {cfg.candles_minimos}", len(serie))

    if cfg.atraso_maximo_minutos is not None and agora is not None:
        atraso = (agora - serie.last.ts).total_seconds() / 60.0
        if atraso > cfg.atraso_maximo_minutos:
            return _corta("dados", titulo,
                          f"ultimo candle de {serie.last.ts:%H:%M}, {atraso:.0f} min atras",
                          atraso)
        return _ok("dados", titulo,
                   f"{len(serie)} candles, ultimo de {serie.last.ts:%H:%M}", len(serie))
    return _ok("dados", titulo, f"{len(serie)} candles carregados", len(serie))


def liquidez(serie: Series, cfg, agora: Optional[datetime] = None) -> Filtro:
    """Volume financeiro medio por pregao - o filtro estrutural."""
    titulo = "liquidez"
    sessoes = serie.sessions()
    if not sessoes:
        return _nao_checado("liquidez", titulo, "nao foi possivel separar os pregoes")

    # o ultimo pregao pode estar em andamento e distorceria a media
    completas = sessoes[:-1] if len(sessoes) > 1 else sessoes
    financeiro = [sum(c.financeiro for c in s) for s in completas]
    media = sum(financeiro) / len(financeiro) if financeiro else 0.0

    if media < cfg.liquidez_minima_diaria:
        return _corta("liquidez", titulo,
                      f"{formata_dinheiro(media)} por pregao, abaixo do minimo de "
                      f"{formata_dinheiro(cfg.liquidez_minima_diaria)}", media)
    return _ok("liquidez", titulo, f"{formata_dinheiro(media)} negociados por pregao", media)


def volume(serie: Series, cfg, agora: Optional[datetime] = None) -> Filtro:
    """Movimento de agora comparado com o proprio historico do ativo."""
    titulo = "volume"
    if len(serie) < 40:
        return _nao_checado("volume", titulo, "serie curta demais para comparar volume")

    recentes = serie.volumes[-20:]
    media_recente = sum(recentes) / len(recentes)
    media_geral = sum(serie.volumes) / len(serie.volumes)
    if media_geral <= 0:
        return _nao_checado("volume", titulo, "serie sem volume registrado")

    relativo = media_recente / media_geral
    if relativo < cfg.volume_relativo_minimo:
        return _corta("volume", titulo,
                      f"volume recente em {relativo:.2f}x a media do ativo - papel parado agora",
                      relativo)
    return _ok("volume", titulo, f"volume recente em {relativo:.2f}x a media do ativo", relativo)


def volatilidade(serie: Series, cfg, agora: Optional[datetime] = None) -> Filtro:
    """ATR em % do preco: nem parado, nem explodindo."""
    titulo = "volatilidade"
    valores = atr_percentual(serie.highs, serie.lows, serie.closes)
    atr_pct = valores[-1] if valores else None
    if atr_pct is None:
        return _nao_checado("volatilidade", titulo, "ATR ainda sem valor")

    if atr_pct < cfg.atr_min_pct:
        return _corta("volatilidade", titulo,
                      f"ATR de {atr_pct:.2f}%, abaixo do minimo de {cfg.atr_min_pct:.2f}%",
                      atr_pct)
    if atr_pct > cfg.atr_max_pct:
        return _corta("volatilidade", titulo,
                      f"ATR de {atr_pct:.2f}%, acima do maximo de {cfg.atr_max_pct:.2f}%",
                      atr_pct)
    return _ok("volatilidade", titulo, f"ATR de {atr_pct:.2f}% do preco", atr_pct)


def spread(serie: Series, cfg, agora: Optional[datetime] = None,
           ticks: Optional[float] = None) -> Filtro:
    """Spread do book, quando alguem informa.

    A serie de candles nao carrega bid/ask. Sem esse dado o filtro sai como
    NAO VERIFICADO - o scanner nao inventa um spread confortavel.
    """
    titulo = "spread"
    if ticks is None:
        return _nao_checado("spread", titulo, "sem book: spread nao informado")
    if ticks > cfg.spread_maximo_ticks:
        return _corta("spread", titulo,
                      f"spread de {ticks:.1f} ticks, acima do maximo de "
                      f"{cfg.spread_maximo_ticks:.1f}", ticks)
    return _ok("spread", titulo, f"spread de {ticks:.1f} ticks", ticks)


FILTROS = (dados_disponiveis, liquidez, volume, volatilidade)


def aplicar(serie: Series, cfg, agora: Optional[datetime] = None,
            spread_ticks: Optional[float] = None) -> list[Filtro]:
    """Roda todos os filtros e devolve o resultado de cada um."""
    resultados = [f(serie, cfg, agora) for f in FILTROS]
    resultados.append(spread(serie, cfg, agora, spread_ticks))
    return resultados
