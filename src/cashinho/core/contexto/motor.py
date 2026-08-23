"""O motor que monta o ``MarketContext``.

Independente de estrategia: o motor nao sabe qual ativo voce vai operar, nao
recebe sinal e nao devolve nada acionavel. Ele le instrumentos, mede e
descreve o ambiente - inclusive quando a descricao honesta e' "nao sei".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from ...data.base import DataError
from ...models import BRT, Series
from . import correlacao as corr
from . import medidas as med
from .fontes import FonteDeContexto
from .instrumentos import CATALOGO, Instrumento, Papel, instrumento as busca_instrumento
from .modelos import (
    DirecaoDeMercado,
    EstadoDaLeitura,
    Leitura,
    MarketContext,
    NivelDeQualidade,
    NivelDeVolatilidade,
    QualidadeDeDados,
    RegimeDeMercado,
)
from .regime import classificar_regime


@dataclass(frozen=True)
class ConfigContexto:
    """O que ler, com que profundidade, e o que conta como dado fresco."""

    instrumentos: tuple[str, ...] = tuple(i.chave for i in CATALOGO)
    timeframe: str = "60m"
    dias: int = 30
    janela_volatilidade: int = 60
    limiar_correlacao: float = corr.LIMIAR_RELEVANTE
    min_amostra_correlacao: int = corr.MIN_AMOSTRA
    defasagem_aceitavel_min: int = 90
    cobertura_boa: float = 0.8
    cobertura_parcial: float = 0.5

    def para_dict(self) -> dict:
        return {
            "instrumentos": list(self.instrumentos),
            "timeframe": self.timeframe,
            "dias": self.dias,
            "limiar_correlacao": self.limiar_correlacao,
            "min_amostra_correlacao": self.min_amostra_correlacao,
            "defasagem_aceitavel_min": self.defasagem_aceitavel_min,
        }


class MotorDeContexto:
    """Le as fontes e monta o contexto de mercado."""

    def __init__(self, fonte: FonteDeContexto, config: Optional[ConfigContexto] = None):
        self.fonte = fonte
        self.config = config or ConfigContexto()

    # ------------------------------------------------------------------
    def montar(
        self,
        instante: Optional[datetime] = None,
        series_do_ativo: Optional[Mapping[str, Series]] = None,
    ) -> MarketContext:
        """Monta o contexto. ``series_do_ativo`` entra so nas correlacoes."""
        agora = instante or datetime.now(BRT)
        leituras: list[Leitura] = []
        series: dict[str, Series] = {}

        for chave in self.config.instrumentos:
            inst = busca_instrumento(chave)
            leitura, serie = self._ler(inst, agora)
            leituras.append(leitura)
            if serie is not None and leitura.mensuravel:
                series[inst.nome] = serie

        ibov = _por_chave(leituras, "ibovespa")
        dolar = _por_chave(leituras, "dolar")
        serie_ibov = series.get(busca_instrumento("ibovespa").nome)

        volatilidade = self._volatilidade(serie_ibov)
        regime, motivos = classificar_regime(
            ibov, dolar, volatilidade,
            [l for l in leituras if l.instrumento.papel is Papel.INDICE_INTERNACIONAL],
        )

        para_correlacao = dict(series)
        para_correlacao.update(series_do_ativo or {})
        correlacoes = corr.correlacoes_relevantes(
            para_correlacao,
            limiar=self.config.limiar_correlacao,
            min_amostra=self.config.min_amostra_correlacao,
            janela=self.config.timeframe,
        )

        qualidade = self._qualidade(leituras)
        notas = list(motivos)
        if qualidade.nivel is NivelDeQualidade.SIMULADA:
            notas.append(
                "dados simulados: este contexto NAO pode pesar em decisao - existe "
                "para a tela e para os testes rodarem sem rede"
            )

        return MarketContext(
            timestamp=agora,
            market_regime=regime,
            ibovespa_direction=ibov.direcao if ibov else DirecaoDeMercado.INDISPONIVEL,
            volatility=volatilidade,
            relevant_correlations=correlacoes,
            data_quality=qualidade,
            leituras=tuple(leituras),
            notas=tuple(notas),
            criterio_correlacao=(
                f"|r| >= {self.config.limiar_correlacao:.2f}".replace(".", ",") +
                f" com ao menos "
                f"{self.config.min_amostra_correlacao} pontos"
            ),
        )

    # ------------------------------------------------------------------
    def _ler(self, inst: Instrumento, agora: datetime) -> tuple[Leitura, Optional[Series]]:
        """Uma leitura por instrumento - com o motivo quando nao da."""
        if not inst.tem_fonte:
            return Leitura(inst, EstadoDaLeitura.SEM_FONTE, detalhe=inst.observacao), None

        if not self.fonte.atende(inst):
            return Leitura(
                inst, EstadoDaLeitura.INDISPONIVEL, fonte=self.fonte.nome,
                detalhe=f"a fonte {self.fonte.nome} nao atende este instrumento",
            ), None

        try:
            serie = self.fonte.serie(inst, self.config.timeframe, self.config.dias)
        except DataError as e:
            return Leitura(
                inst, EstadoDaLeitura.INDISPONIVEL, fonte=self.fonte.nome, detalhe=str(e),
            ), None

        if not len(serie):
            return Leitura(
                inst, EstadoDaLeitura.INDISPONIVEL, fonte=self.fonte.nome,
                detalhe="a fonte respondeu sem candles",
            ), None

        ultimo = serie.candles[-1]
        atraso = med.defasagem_minutos(ultimo.ts, agora)
        variacao = med.variacao_do_dia(serie)

        if self.fonte.simulada:
            estado = EstadoDaLeitura.SIMULADA
        elif atraso is not None and atraso > self._defasagem_tolerada(inst):
            estado = EstadoDaLeitura.ATRASADA
        else:
            estado = EstadoDaLeitura.OK

        return Leitura(
            instrumento=inst, estado=estado, ultimo=ultimo.close, variacao_pct=variacao,
            ts=ultimo.ts, defasagem_minutos=atraso, fonte=self.fonte.nome,
        ), serie

    def _defasagem_tolerada(self, inst: Instrumento) -> int:
        """Serie diaria nao envelhece na mesma escala que intradiario."""
        if not inst.intradiario:
            return 60 * 24 * 4  # ate quatro dias: feriado prolongado nao e' falha
        return self.config.defasagem_aceitavel_min

    def _volatilidade(self, serie_ibov: Optional[Series]) -> NivelDeVolatilidade:
        if serie_ibov is None:
            return NivelDeVolatilidade.INDISPONIVEL
        janela = self.config.janela_volatilidade
        atual = med.volatilidade_por_candle(serie_ibov, janela)
        referencia = med.volatilidade_historica(serie_ibov, janela)
        return med.classificar_volatilidade(atual, referencia)

    def _qualidade(self, leituras: Sequence[Leitura]) -> QualidadeDeDados:
        com_fonte = [l for l in leituras if l.estado is not EstadoDaLeitura.SEM_FONTE]
        sem_fonte = tuple(l.instrumento.nome for l in leituras
                          if l.estado is EstadoDaLeitura.SEM_FONTE)
        disponiveis = [l for l in com_fonte if l.mensuravel]
        faltantes = tuple(l.instrumento.nome for l in com_fonte if not l.mensuravel)
        simuladas = [l for l in leituras if l.estado is EstadoDaLeitura.SIMULADA]

        atrasos = [l.defasagem_minutos for l in disponiveis if l.defasagem_minutos is not None]
        atraso = max(atrasos) if atrasos else None
        notas: list[str] = []
        if sem_fonte:
            notas.append(
                f"{len(sem_fonte)} instrumento(s) sem fonte confiavel: "
                f"{', '.join(sem_fonte)} - nao sao estimados"
            )

        esperados = len(com_fonte)
        if simuladas:
            return QualidadeDeDados(
                NivelDeQualidade.SIMULADA, len(simuladas), esperados, faltantes,
                sem_fonte, atraso,
                tuple(notas + ["fonte de demonstracao: nao sao cotacoes reais"]),
            )
        if not disponiveis:
            return QualidadeDeDados(
                NivelDeQualidade.INDISPONIVEL, 0, esperados, faltantes, sem_fonte,
                None, tuple(notas + ["nenhuma fonte respondeu"]),
            )

        cobertura = len(disponiveis) / esperados if esperados else 0.0
        atrasado = atraso is not None and atraso > self.config.defasagem_aceitavel_min
        if atrasado:
            notas.append(f"o dado mais velho tem {atraso} min de atraso")

        if cobertura >= self.config.cobertura_boa and not atrasado:
            nivel = NivelDeQualidade.BOA
        elif cobertura >= self.config.cobertura_parcial:
            nivel = NivelDeQualidade.PARCIAL
        else:
            nivel = NivelDeQualidade.RUIM
        return QualidadeDeDados(nivel, len(disponiveis), esperados, faltantes,
                                sem_fonte, atraso, tuple(notas))


def _por_chave(leituras: Sequence[Leitura], chave: str) -> Optional[Leitura]:
    for l in leituras:
        if l.chave == chave:
            return l
    return None
