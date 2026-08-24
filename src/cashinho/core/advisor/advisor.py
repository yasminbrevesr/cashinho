"""``TimeframeAdvisor``: qual timeframe serve para operar este ativo agora.

Nao e' "qual timeframe ganhou mais hoje". A pergunta e' outra: **o
comportamento atual do ativo favorece qual granularidade** - e ha evidencia
para afirmar isso?

    candles de 1m
        -> reamostragem (MTFEngine, ja existente)
        -> medidas por timeframe, so com candle FECHADO ate o instante
        -> seis notas explicaveis
        -> market fit  /  statistical evidence  /  confidence
        -> histerese
        -> TimeframeRecommendation

Independente de provider: entra uma ``Series`` de 1m, venha ela do
MetaTrader, de CSV, do replay ou do backtest. Este modulo **nao importa
MetaTrader5** - ha teste para isso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from ...models import BRT, Series
from ..mtf import MTFConfig, MTFEngine
from ..structure import EstruturaConfig, analisar_estrutura
from ..structure.models import Regime
from .amostra import Confianca, Estatistica, NivelDeConfianca, calcular_confianca
from .estabilidade import ConfigEstabilidade, Decisao, RecomendacaoAtual, decidir
from .medidas import MIN_CANDLES, medir
from .modelos import ItemDoRanking, StatusAdvisor, TimeframeRecommendation
from .periodos import PeriodoDoPregao, periodo_de
from .score import PESOS_PADRAO, PesosAdvisor, calcular

# candidatos a timeframe de SETUP - onde a operacao e' desenhada
SETUP_CANDIDATOS = ("1m", "2m", "3m", "5m", "10m", "15m")
# candidatos a CONTEXTO - onde se le a direcao maior
CONTEXTO_CANDIDATOS = ("15m", "30m", "60m")
# o gatilho e' sempre mais fino que o setup
GATILHO_CANDIDATOS = ("1m", "2m", "3m", "5m")

MINIMO_PARA_AVALIAR = 30


@dataclass(frozen=True)
class ConfigAdvisor:
    """O que o Advisor considera - tudo configuravel."""

    setup: tuple[str, ...] = SETUP_CANDIDATOS
    contexto: tuple[str, ...] = CONTEXTO_CANDIDATOS
    gatilho: tuple[str, ...] = GATILHO_CANDIDATOS
    pesos: PesosAdvisor = PESOS_PADRAO
    estabilidade: ConfigEstabilidade = field(default_factory=ConfigEstabilidade)
    confianca_minima: float = 15.0
    janela_de_candles: int = 400
    estrutura: EstruturaConfig = field(default_factory=EstruturaConfig)

    def para_dict(self) -> dict:
        return {
            "setup": list(self.setup), "contexto": list(self.contexto),
            "gatilho": list(self.gatilho), "pesos": self.pesos.para_dict(),
            "estabilidade": self.estabilidade.para_dict(),
            "confianca_minima": self.confianca_minima,
        }


class TimeframeAdvisor:
    """Avalia os timeframes candidatos e recomenda a combinacao."""

    def __init__(self, config: Optional[ConfigAdvisor] = None, log=None):
        from ..log import RegistradorNulo

        self.config = config or ConfigAdvisor()
        self.log = log or RegistradorNulo()

    # ------------------------------------------------------------------
    def avaliar(
        self,
        serie_base: Series,
        as_of: Optional[datetime] = None,
        atual: Optional[RecomendacaoAtual] = None,
        estatisticas: Optional[Mapping[str, Estatistica]] = None,
        spread: Optional[float] = None,
    ) -> TimeframeRecommendation:
        """A recomendacao no instante ``as_of``, so com o que existia ate la.

        ``serie_base`` deve ser a serie de 1m; os demais timeframes saem da
        reamostragem. ``estatisticas`` e' o historico por timeframe, quando
        houver - sem ele, a evidencia estatistica fica indisponivel em vez de
        inventada.
        """
        symbol = serie_base.symbol
        estatisticas = dict(estatisticas or {})

        if not len(serie_base):
            return self._sem_dados(symbol, as_of or datetime.now(BRT),
                                   "serie base vazia")

        instante = as_of or serie_base.candles[-1].ts
        periodo = periodo_de(instante)

        # a vista do MTF e' quem garante o corte no instante: barra que ainda
        # nao fechou nao aparece, e isso ja e' testado no proprio modulo
        vista = self._vista(serie_base, instante)

        regime_contexto, tf_contexto = self._contexto(vista)
        rankings = self._ranquear(vista, regime_contexto, estatisticas, spread)

        if not rankings:
            return self._sem_dados(symbol, instante,
                                   "nenhum timeframe com candles suficientes",
                                   periodo, regime_contexto)

        lider = rankings[0]
        vantagem = (lider.total - rankings[1].total) if len(rankings) > 1 else None
        confianca = calcular_confianca(
            lider.medidas.candles, estatisticas.get(lider.timeframe),
            lider.score.indisponiveis, vantagem)

        decisao = decidir(lider.timeframe, lider.total, atual, instante,
                          self.config.estabilidade,
                          score_do_atual=self._score_de(rankings, atual))
        escolhido = decisao.timeframe if atual is not None else lider.timeframe
        item = next((r for r in rankings if r.timeframe == escolhido), lider)

        status = self._status(confianca, decisao, atual)
        gatilho = self._gatilho(escolhido, rankings) if status.acionavel else None
        return TimeframeRecommendation(
            symbol=symbol,
            as_of=instante,
            status=status,
            context_timeframe=tf_contexto if status.acionavel else None,
            setup_timeframe=escolhido if status.acionavel else None,
            trigger_timeframe=gatilho,
            market_fit_score=item.market_fit,
            statistical_evidence_score=item.statistical_evidence,
            confidence_score=confianca.valor,
            confianca=confianca,
            rankings=tuple(rankings),
            reasons=self._motivos(item, decisao, periodo, regime_contexto, status),
            warnings=self._avisos(item, confianca, rankings,
                                  sem_gatilho=status.acionavel and gatilho is None),
            periodo=periodo,
            regime=regime_contexto.value if regime_contexto else None,
            decisao=decisao if atual is not None else None,
        )

    # ------------------------------------------------------------------
    def _vista(self, serie_base: Series, instante: datetime):
        camadas = {f"tf_{tf}": tf for tf in
                   dict.fromkeys((*self.config.setup, *self.config.contexto,
                                  *self.config.gatilho))}
        engine = MTFEngine(MTFConfig(base=serie_base.timeframe or "1m",
                                     camadas=camadas), serie_base.symbol)
        return engine.alimentar(serie_base).em(instante)

    def _contexto(self, vista) -> tuple[Optional[Regime], Optional[str]]:
        """O maior timeframe de contexto com estrutura legivel manda."""
        for tf in self.config.contexto:
            serie = vista.fechados(tf, limite=self.config.janela_de_candles)
            if len(serie) < MINIMO_PARA_AVALIAR:
                continue
            try:
                estrutura = analisar_estrutura(serie, self.config.estrutura)
            except ValueError:
                continue
            return estrutura.tendencia.regime, tf
        return None, None

    def _ranquear(self, vista, regime_contexto, estatisticas, spread) -> list[ItemDoRanking]:
        itens: list[ItemDoRanking] = []
        for tf in self.config.setup:
            serie = vista.fechados(tf, limite=self.config.janela_de_candles)
            if len(serie) < MIN_CANDLES:
                continue

            estrutura = None
            try:
                estrutura = analisar_estrutura(serie, self.config.estrutura)
            except ValueError:
                pass

            medidas = medir(serie, estrutura, spread)
            estatistica = estatisticas.get(tf)
            score = calcular(medidas, regime_contexto, estatistica, self.config.pesos)
            confianca = calcular_confianca(medidas.candles, estatistica,
                                           score.indisponiveis)
            itens.append(ItemDoRanking(tf, score, medidas, confianca, estatistica))

        # ordenacao deterministica: score, depois market fit, depois o rotulo -
        # empate nunca pode depender da ordem em que o dicionario foi montado
        itens.sort(key=lambda i: (-i.total, -i.market_fit, i.timeframe))
        return itens

    def _gatilho(self, setup: str, rankings: Sequence[ItemDoRanking]) -> Optional[str]:
        """O melhor timeframe **mais fino** que o setup.

        Gatilho igual ou maior que o setup nao e' gatilho: seria decidir a
        entrada na mesma granularidade em que se desenhou a operacao.
        """
        from ..mtf.timeframes import parse_timeframe

        minutos_setup = parse_timeframe(setup).minutos
        candidatos = [r for r in rankings
                      if r.timeframe in self.config.gatilho
                      and parse_timeframe(r.timeframe).minutos < minutos_setup]
        # sem nada mais fino, NAO ha gatilho. Repetir o setup aqui sugeriria
        # uma camada de confirmacao que nao existe
        return candidatos[0].timeframe if candidatos else None

    def _score_de(self, rankings, atual) -> Optional[float]:
        if atual is None:
            return None
        for r in rankings:
            if r.timeframe == atual.timeframe:
                return r.total
        return None

    def _status(self, confianca: Confianca, decisao: Decisao, atual) -> StatusAdvisor:
        if confianca.nivel is NivelDeConfianca.INSUFICIENTE:
            return StatusAdvisor.DADOS_INSUFICIENTES
        if confianca.valor < self.config.confianca_minima:
            return StatusAdvisor.CONFIANCA_BAIXA
        if atual is not None and decisao.manter:
            return StatusAdvisor.MANTER_ATUAL
        return StatusAdvisor.RECOMENDADO

    def _motivos(self, item, decisao, periodo, regime, status) -> tuple[str, ...]:
        motivos = [f"periodo: {periodo.rotulo.lower()} ({periodo.descricao})"]
        if regime is not None:
            motivos.append(f"contexto em {regime.value}")
        for c in item.score.melhores(2):
            motivos.append(f"{c.nome} {c.nota:.0f}: {c.leitura}")
        if decisao is not None and decisao.motivo:
            motivos.append(decisao.motivo)
        if status is StatusAdvisor.CONFIANCA_BAIXA:
            motivos.append("ha um lider no ranking, mas nao ha sustentacao "
                           "para transformar isso em recomendacao")
        return tuple(motivos)

    def _avisos(self, item, confianca: Confianca, rankings,
                sem_gatilho: bool = False) -> tuple[str, ...]:
        avisos = list(confianca.motivos)
        for c in item.score.piores(2):
            if c.nota < 45:
                avisos.append(f"{c.nome} fraco ({c.nota:.0f}): {c.leitura}")
        if sem_gatilho:
            avisos.append("setup no timeframe mais fino disponivel: nao ha "
                          "granularidade menor para servir de gatilho")
        if item.statistical_evidence is None:
            avisos.append("market fit alto nao e' evidencia estatistica: "
                          "sem historico, isto e' leitura de comportamento, "
                          "nao conclusao")
        return tuple(avisos)

    def _sem_dados(self, symbol, instante, motivo, periodo=PeriodoDoPregao.FORA,
                   regime=None) -> TimeframeRecommendation:
        return TimeframeRecommendation(
            symbol=symbol, as_of=instante, status=StatusAdvisor.DADOS_INSUFICIENTES,
            warnings=(motivo,), periodo=periodo,
            regime=regime.value if regime else None,
            reasons=(f"nao ha o que recomendar: {motivo}",))
