"""O Opportunity Engine: da leitura multi-timeframe a uma oportunidade pontuada.

Fluxo, em uma frase: o motor de confluencia diz **se** ha setup e para que
lado; o Opportunity Engine calcula os niveis, roda os onze componentes do
score, define o prazo de validade e carimba o estado.

Sempre devolve uma :class:`Opportunity` - inclusive quando nao ha o que
fazer. Silencio nao explica nada; ``NAO OPERAR`` com o motivo, sim. Mas so o
estado ``SETUP APROVADO`` e' acionavel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

from ...models import Direction, Series, formata_dinheiro
from ..confluencia import MultiTimeframeEngine
from ..confluencia.estados import SetupState, TriggerState, Vies
from ..confluencia.modelos import LeituraMultiTimeframe
from ..mtf.timeframes import parse_timeframe
from ..structure import EstruturaConfig, analisar_estrutura
from ..structure.models import MarketStructure
from .estados import EstadoOportunidade
from .modelos import Opportunity
from .score import (
    PESOS_PADRAO,
    ConfigScore,
    Penalidade,
    PesosScore,
    ScoreDetalhado,
    calcular,
    montar_contexto,
)


@dataclass(frozen=True)
class ConfigOportunidade:
    """Criterios de aprovacao e de validade."""

    score_minimo: float = 60.0
    rr_minimo: float = 1.5
    stop_atr: float = 1.5
    alvo_em_r: float = 2.0
    expiracao_candles_gatilho: int = 3
    idade_maxima_contexto_min: float = 180.0  # vira aviso, nao reprovacao
    # Pisos por componente. A media ponderada, sozinha, deixa uma falha
    # critica ser voto vencido: um alvo que atravessa uma resistencia colada
    # na entrada pode passar se o resto for bom. Abaixo destes pisos, o setup
    # e' rejeitado por mais alto que esteja o score.
    notas_minimas: dict = field(
        default_factory=lambda: {
            "gatilho": 30.0,
            "risco_retorno": 25.0,
            "suporte_resistencia": 20.0,
        }
    )
    estrutura: EstruturaConfig = field(default_factory=EstruturaConfig)
    score: ConfigScore = field(default_factory=ConfigScore)

    def __post_init__(self) -> None:
        if not 0 <= self.score_minimo <= 100:
            raise ValueError("score_minimo precisa ficar entre 0 e 100")
        if self.rr_minimo <= 0:
            raise ValueError("rr_minimo precisa ser maior que zero")
        if self.expiracao_candles_gatilho < 1:
            raise ValueError("expiracao_candles_gatilho precisa ser pelo menos 1")


class OpportunityEngine:
    """Monta, pontua e classifica oportunidades."""

    def __init__(
        self,
        confluencia: Optional[MultiTimeframeEngine] = None,
        pesos: Optional[PesosScore] = None,
        config: Optional[ConfigOportunidade] = None,
        janela: int = 400,
        eventos=None,
    ):
        self.confluencia = confluencia or MultiTimeframeEngine()
        self.pesos = pesos or PESOS_PADRAO
        self.config = config or ConfigOportunidade()
        self.janela = janela
        # avaliador de noticias e eventos (opcional). Ele so sabe descontar
        # score, aumentar risco e bloquear - nunca aprovar
        self.eventos = eventos
        self._cache_estrutura: dict = {}

    # ------------------------------------------------------------------
    def avaliar(self, vista, symbol: str = "") -> Opportunity:
        """Avalia o instante da vista e devolve a oportunidade com estado."""
        resultado = self.confluencia.avaliar(vista, symbol)
        leitura = resultado.leitura
        agora = leitura.instante
        tfs = self._timeframes()

        # --- o mercado esta em condicao de operar este ativo? ------------
        if leitura.faltando:
            return self._sem_operacao(
                leitura, tfs,
                f"camadas ainda sem candle fechado: {', '.join(leitura.faltando)}",
            )

        direcao = self._direcao(leitura, resultado)
        if direcao is None:
            return self._sem_operacao(leitura, tfs, "nenhuma camada define uma direcao")

        serie_setup = vista.fechados(tfs["setup"], limite=self.janela)
        serie_trigger = vista.fechados(tfs["trigger"], limite=self.janela)
        if len(serie_setup) < 5 or len(serie_trigger) < 2:
            return self._sem_operacao(leitura, tfs, "series curtas demais para avaliar")

        estrutura = self._estrutura(serie_setup)
        entry, stop, target = self._niveis(direcao, serie_trigger, estrutura)
        if abs(entry - stop) <= 0:
            return self._sem_operacao(leitura, tfs, "nao foi possivel posicionar o stop")

        ctx = montar_contexto(
            direcao=direcao, leitura=leitura, estrutura=estrutura,
            serie_setup=serie_setup, serie_trigger=serie_trigger,
            entry=entry, stop=stop, target=target, cfg=self.config.score,
        )
        detalhado = calcular(ctx, self.pesos)

        # a agenda entra ANTES do estado ser decidido: o desconto de score e o
        # bloqueio precisam valer na mesma conta que aprova ou rejeita
        eventos = self._eventos(leitura.symbol, agora, direcao)
        if eventos is not None and eventos.ajuste_de_score:
            detalhado = detalhado.com_penalidade(Penalidade(
                "eventos", "Noticias e eventos", -eventos.ajuste_de_score,
                "; ".join(e.event_type.curto + " " + e.alvo for e in eventos.eventos[:3]),
            ))

        avisos = self._avisos(leitura, ctx, detalhado)
        if eventos is not None:
            avisos = avisos + tuple(eventos.avisos)
        estado, motivo = self._estado(resultado, leitura, detalhado, ctx)
        if eventos is not None and eventos.bloqueado:
            # bloqueio so rebaixa: ele nunca promove um estado
            estado, motivo = EstadoOportunidade.NAO_OPERAR, eventos.motivo

        candidata = resultado.candidata
        return Opportunity(
            symbol=leitura.symbol,
            timestamp=agora,
            direction=direcao,
            setup=self._descricao_do_setup(leitura, candidata),
            score=detalhado.total,
            entry=entry,
            stop=stop,
            target=target,
            risk_reward=round(ctx.rr, 3),
            timeframe_context=tfs["context"],
            timeframe_trend=tfs["trend"],
            timeframe_setup=tfs["setup"],
            timeframe_trigger=tfs["trigger"],
            reasons=self._razoes(leitura, candidata, detalhado),
            warnings=avisos,
            invalidation=self._invalidacao(leitura, direcao, stop),
            expires_at=self._expira_em(agora, tfs["trigger"]),
            estado=estado,
            score_detalhado=detalhado,
            leitura=leitura,
            regra=candidata.regra if candidata else "",
            motivo_do_estado=motivo,
            eventos=eventos,
        )

    # ------------------------------------------------------------------
    # partes
    # ------------------------------------------------------------------
    def _estrutura(self, serie_setup: Series) -> MarketStructure:
        """A estrutura do setup so muda quando um candle DELE fecha.

        Sem este cache, um backtest de 1m recalcularia pivos, zonas e
        Fibonacci a cada minuto sobre a mesma serie de 5m.
        """
        # o symbol faz parte da chave: numa varredura, dois ativos tem o
        # mesmo timeframe, o mesmo ultimo candle e o mesmo tamanho de serie
        chave = (serie_setup.symbol, serie_setup.timeframe, serie_setup.last.ts, len(serie_setup))
        if chave not in self._cache_estrutura:
            self._cache_estrutura[chave] = analisar_estrutura(serie_setup, self.config.estrutura)
        return self._cache_estrutura[chave]

    def _timeframes(self) -> dict[str, str]:
        camadas = self.confluencia.config.camadas
        return {papel: camadas.get(papel, "-") for papel in
                ("context", "trend", "setup", "trigger")}

    def _direcao(self, leitura: LeituraMultiTimeframe, resultado) -> Optional[Direction]:
        """A direcao vem da regra que fechou; sem regra, do setup."""
        if resultado.candidata is not None:
            return resultado.candidata.direcao
        setup = leitura.camada("setup")
        if setup is not None and setup.vies is not Vies.NEUTRAL:
            return setup.vies.direcao
        trend = leitura.camada("trend")
        if trend is not None and trend.vies is not Vies.NEUTRAL:
            return trend.vies.direcao
        return None

    def _niveis(self, direcao: Direction, serie_trigger: Series,
                estrutura: MarketStructure) -> tuple[float, float, float]:
        cfg = self.config
        entry = serie_trigger.price
        atr = estrutura.atr or entry * 0.005
        if direcao is Direction.LONG:
            apoio = estrutura.suporte.mid if estrutura.suporte else None
            stop = min(apoio, entry - cfg.stop_atr * atr) if apoio else entry - cfg.stop_atr * atr
            target = entry + cfg.alvo_em_r * (entry - stop)
            # o alvo tem que ser alcancavel: nao adianta projetar 2R do outro
            # lado de uma resistencia. Sem espaco, o RR cai e o setup e'
            # rejeitado - que e' a leitura honesta da situacao.
            parede = estrutura.resistencia
            if parede is not None and parede.low > entry:
                target = min(target, parede.low - 0.1 * atr)
        else:
            apoio = estrutura.resistencia.mid if estrutura.resistencia else None
            stop = max(apoio, entry + cfg.stop_atr * atr) if apoio else entry + cfg.stop_atr * atr
            target = entry - cfg.alvo_em_r * (stop - entry)
            parede = estrutura.suporte
            if parede is not None and parede.high < entry:
                target = max(target, parede.high + 0.1 * atr)
        return entry, stop, target

    def _expira_em(self, agora: datetime, tf_trigger: str) -> datetime:
        minutos = parse_timeframe(tf_trigger).minutos or 5
        return agora + timedelta(minutes=minutos * self.config.expiracao_candles_gatilho)

    def _eventos(self, symbol: str, agora: datetime, direcao):
        """A leitura da agenda de eventos - ou None quando nao ha avaliador."""
        if self.eventos is None:
            return None
        return self.eventos.avaliar(symbol, agora, direcao)

    def _estado(self, resultado, leitura: LeituraMultiTimeframe,
                detalhado: ScoreDetalhado, ctx) -> tuple[EstadoOportunidade, str]:
        cfg = self.config
        setup = leitura.camada("setup")
        trigger = leitura.camada("trigger")

        if setup is None or not setup.estado.existe:
            return (EstadoOportunidade.NAO_OPERAR,
                    f"sem formacao no {setup.timeframe if setup else 'setup'}")

        if resultado.candidata is None:
            regra = self._so_falta_o_gatilho(resultado)
            if regra is not None and trigger is not None:
                return (EstadoOportunidade.AGUARDANDO_GATILHO,
                        f"setup {setup.valor} pronto no {setup.timeframe} para a regra "
                        f"'{regra}', aguardando gatilho no {trigger.timeframe}")
            return (EstadoOportunidade.REJEITADO, self._porque_nenhuma_regra_fechou(resultado))

        abaixo_do_piso = self._piso_violado(detalhado)
        if abaixo_do_piso is not None:
            componente, piso = abaixo_do_piso
            return (EstadoOportunidade.REJEITADO,
                    f"{componente.nome} com nota {componente.nota:.0f}, abaixo do piso de "
                    f"{piso:.0f}: {componente.leitura}")

        if detalhado.total < cfg.score_minimo:
            piores = ", ".join(f"{c.nome} {c.nota:.0f}" for c in detalhado.piores(2))
            return (EstadoOportunidade.REJEITADO,
                    f"score {detalhado.total:.0f} abaixo do minimo de {cfg.score_minimo:.0f} "
                    f"(pesa contra: {piores})")
        if ctx.rr < cfg.rr_minimo:
            return (EstadoOportunidade.REJEITADO,
                    f"risco/retorno de {ctx.rr:.2f} abaixo do minimo de {cfg.rr_minimo:.2f}")

        return (EstadoOportunidade.APROVADO,
                f"regra '{resultado.candidata.regra}' fechou com score {detalhado.total:.0f}")

    def _piso_violado(self, detalhado: ScoreDetalhado):
        """Primeiro componente critico abaixo do piso configurado."""
        for chave, piso in self.config.notas_minimas.items():
            componente = detalhado.componente(chave)
            if componente is not None and componente.nota < piso:
                return componente, piso
        return None

    def _so_falta_o_gatilho(self, resultado) -> Optional[str]:
        """Ha regra em que tudo bateu e a unica pendencia e' o gatilho?

        Alinhamento, coerencia e confianca sao consequencia do gatilho: com
        ele ausente, o vies dele e' neutro e a forca media cai. Falhar nesses
        tres nao significa que o setup nao esta pronto - significa que ainda
        falta o gatilho.
        """
        consequencias = {"trigger", "alinhamento", "coerencia", "confianca"}
        for a in resultado.avaliacoes:
            checagens = {c.papel: c for c in a.checagens}
            setup = checagens.get("setup")
            gatilho = checagens.get("trigger")
            if setup is None or not setup.ok:
                continue
            if gatilho is None or gatilho.ok:
                continue
            if all(c.ok for c in a.checagens if c.papel not in consequencias):
                return a.regra.nome
        return None

    def _porque_nenhuma_regra_fechou(self, resultado) -> str:
        for a in resultado.avaliacoes:
            if a.falhas:
                f = a.falhas[0]
                return (f"nenhuma regra fechou - em '{a.regra.nome}', {f.papel} = "
                        f"{f.obtido or '-'} (esperado {'/'.join(f.esperado)})")
        return "nenhuma regra de confluencia fechou"

    def _descricao_do_setup(self, leitura: LeituraMultiTimeframe, candidata) -> str:
        if candidata is not None:
            return candidata.regra
        setup = leitura.camada("setup")
        return f"{setup.timeframe}: {setup.valor}" if setup else "sem setup"

    def _razoes(self, leitura: LeituraMultiTimeframe, candidata,
                detalhado: ScoreDetalhado) -> tuple[str, ...]:
        if candidata is not None:
            base = list(candidata.razoes)
        else:
            base = [f"{c.timeframe}: {c.papel} = {c.valor}" for c in leitura.camadas]
        melhores = detalhado.por_contribuicao()[:3]
        base += [f"{c.nome} {c.nota:.0f}/100 - {c.leitura}" for c in melhores]
        return tuple(dict.fromkeys(base))

    def _avisos(self, leitura: LeituraMultiTimeframe, ctx, detalhado: ScoreDetalhado) -> tuple[str, ...]:
        avisos: list[str] = []
        contexto = leitura.camada("context")
        if contexto is not None and contexto.idade_minutos > self.config.idade_maxima_contexto_min:
            avisos.append(
                f"o contexto de {contexto.timeframe} tem {contexto.idade_minutos / 60:.1f} h - "
                "pode nao refletir o mercado agora"
            )
        if ctx.rr < 2.0:
            avisos.append(f"risco/retorno de {ctx.rr:.2f}: pouca margem para erro")
        for c in detalhado.piores(3):
            if c.nota < 40:
                avisos.append(f"{c.nome} fraco ({c.nota:.0f}/100): {c.leitura}")
        if ctx.estrutura.fib is None:
            avisos.append("sem grade de Fibonacci: nao ha swing valido para ancorar")
        return tuple(dict.fromkeys(avisos))

    def _invalidacao(self, leitura: LeituraMultiTimeframe, direcao: Direction, stop: float) -> str:
        partes = [f"perder {formata_dinheiro(stop)}"]
        trend = leitura.camada("trend")
        if trend is not None:
            partes.append(f"a tendencia de {trend.timeframe} virar")
        setup = leitura.camada("setup")
        if setup is not None:
            partes.append(f"o setup de {setup.timeframe} desmanchar")
        partes.append("ou a janela de validade expirar")
        return "; ".join(partes)

    def _sem_operacao(self, leitura: LeituraMultiTimeframe, tfs: dict, motivo: str) -> Opportunity:
        return Opportunity(
            symbol=leitura.symbol,
            timestamp=leitura.instante,
            direction=None,
            setup="-",
            score=0.0,
            entry=0.0, stop=0.0, target=0.0, risk_reward=0.0,
            timeframe_context=tfs["context"], timeframe_trend=tfs["trend"],
            timeframe_setup=tfs["setup"], timeframe_trigger=tfs["trigger"],
            reasons=(motivo,),
            warnings=tuple(leitura.avisos),
            invalidation="-",
            expires_at=None,
            estado=EstadoOportunidade.NAO_OPERAR,
            leitura=leitura,
            motivo_do_estado=motivo,
        )

    # ------------------------------------------------------------------
    def alimentar(self, serie_base: Series):
        """Atalho: monta o motor de alinhamento com a configuracao deste engine."""
        return self.confluencia.alimentar(serie_base)
