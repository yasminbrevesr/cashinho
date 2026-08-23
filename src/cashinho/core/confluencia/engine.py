"""O Multi-Timeframe Engine: le as quatro camadas e aplica as regras.

Duas metades, deliberadamente separadas:

- **alinhamento** (``cashinho.core.mtf``): quais candles ja fecharam em cada
  timeframe naquele instante. E' de la que vem a garantia de que nenhuma
  camada enxerga o futuro;
- **leitura e regras** (aqui): o que cada camada significa e quando a
  combinacao autoriza uma :class:`Opportunity`.

Uso::

    engine = MultiTimeframeEngine()            # 60m/15m/5m/1m
    resultado = engine.avaliar(vista, "PETR4")

    resultado.leitura.context.estado           # ContextState.BULLISH
    resultado.oportunidade                     # None enquanto nenhuma regra fechar

Todas as camadas sao lidas do MESMO ``MTFVista``, entao carregam o mesmo
``lido_em``. Uma camada que ainda nao tem candle fechado nao vira "neutra por
falta de dado": ela entra em ``faltando`` e nenhuma regra que a exige pode
ser satisfeita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from ...models import Direction, Series, formata_dinheiro
from ..mtf import MTFConfig, MTFEngine, MTFError
from ..mtf.engine import MTFVista
from .estados import PAPEIS_PADRAO, Vies
from .leitura import LEITORES, ConfigLeitura
from .modelos import Camada, LeituraMultiTimeframe, Opportunity
from .regras import REGRAS_PADRAO, AvaliacaoRegra, RegraOportunidade

CAMADAS_CONFLUENCIA = {"context": "60m", "trend": "15m", "setup": "5m", "trigger": "1m"}
"""A combinacao do enunciado. Trocavel: e' so passar outro MTFConfig."""


def config_padrao(base: str = "1m") -> MTFConfig:
    """60m contexto, 15m tendencia, 5m setup, 1m gatilho."""
    return MTFConfig(base=base, camadas=dict(CAMADAS_CONFLUENCIA))


@dataclass
class ResultadoConfluencia:
    """O que o engine devolve em cada instante."""

    leitura: LeituraMultiTimeframe
    avaliacoes: list[AvaliacaoRegra] = field(default_factory=list)
    oportunidade: Optional[Opportunity] = None

    @property
    def tem_oportunidade(self) -> bool:
        return self.oportunidade is not None

    @property
    def satisfeitas(self) -> list[AvaliacaoRegra]:
        return [a for a in self.avaliacoes if a.satisfeita]

    def avaliacao(self, nome: str) -> Optional[AvaliacaoRegra]:
        for a in self.avaliacoes:
            if a.regra.nome == nome:
                return a
        return None

    def para_dict(self) -> dict:
        return {
            "leitura": self.leitura.para_dict(),
            "avaliacoes": [a.para_dict() for a in self.avaliacoes],
            "oportunidade": self.oportunidade.para_dict() if self.oportunidade else None,
        }


class MultiTimeframeEngine:
    """Le contexto, tendencia, setup e gatilho de uma vista e aplica as regras."""

    def __init__(
        self,
        config: Optional[MTFConfig] = None,
        regras: Sequence[RegraOportunidade] = REGRAS_PADRAO,
        leitura: Optional[ConfigLeitura] = None,
        janela: int = 400,
    ):
        self.config = config or config_padrao()
        self.regras = tuple(regras)
        self.cfg_leitura = leitura or ConfigLeitura()
        self.janela = janela
        self._cache: dict = {}
        self._validar_papeis()

    def _validar_papeis(self) -> None:
        desconhecidos = set(self.config.camadas) - set(LEITORES)
        if desconhecidos:
            raise MTFError(
                f"papeis sem leitor: {', '.join(sorted(desconhecidos))} "
                f"(disponiveis: {', '.join(sorted(LEITORES))})"
            )

    @property
    def papeis(self) -> list[str]:
        """Papeis configurados, do maior timeframe para o menor."""
        return self.config.papeis()

    # ------------------------------------------------------------------
    # leitura
    # ------------------------------------------------------------------
    def ler(self, vista: MTFVista, symbol: str = "") -> LeituraMultiTimeframe:
        """Le todas as camadas no instante da vista."""
        instante = vista.instante
        camadas: list[Camada] = []
        faltando: list[str] = []
        avisos: list[str] = []

        for papel in self.papeis:
            timeframe = self.config.timeframe(papel).rotulo
            barras = vista.barras_fechadas(timeframe, limite=self.janela)
            if not barras:
                faltando.append(papel)
                avisos.append(
                    f"{papel} ({timeframe}): nenhum candle fechado ate "
                    f"{instante:%d/%m %H:%M} - a camada nao existe ainda"
                )
                continue

            fechado_em = barras[-1].fim
            serie = Series(symbol or vista._engine.symbol, timeframe, [b.candle for b in barras])
            chave = (papel, timeframe, fechado_em)
            if chave not in self._cache:
                # a leitura de uma camada so muda quando o candle DELA fecha:
                # guardar por (papel, fechamento) evita recalcular a cada tick
                self._cache[chave] = LEITORES[papel](serie, fechado_em, fechado_em, self.cfg_leitura)
            base = self._cache[chave]
            camadas.append(
                type(base)(
                    papel=base.papel, timeframe=base.timeframe, estado=base.estado,
                    ts=base.ts, fechado_em=base.fechado_em, lido_em=instante,
                    forca=base.forca, razoes=base.razoes, detalhes=base.detalhes,
                )
            )

        return LeituraMultiTimeframe(
            symbol=symbol or vista._engine.symbol,
            instante=instante,
            camadas=tuple(camadas),
            faltando=tuple(faltando),
            avisos=tuple(avisos),
        )

    # ------------------------------------------------------------------
    # regras
    # ------------------------------------------------------------------
    def avaliar(self, vista: MTFVista, symbol: str = "") -> ResultadoConfluencia:
        """Le as camadas e devolve a oportunidade - se alguma regra fechar."""
        leitura = self.ler(vista, symbol)
        avaliacoes = [regra.avaliar(leitura) for regra in self.regras]
        satisfeitas = [a for a in avaliacoes if a.satisfeita]

        oportunidade = None
        if satisfeitas:
            melhor = max(satisfeitas, key=lambda a: a.confianca)
            oportunidade = self._montar(leitura, melhor)

        return ResultadoConfluencia(leitura=leitura, avaliacoes=avaliacoes, oportunidade=oportunidade)

    def _montar(self, leitura: LeituraMultiTimeframe, avaliacao: AvaliacaoRegra) -> Opportunity:
        direcao = avaliacao.vies.direcao
        niveis = self._niveis(leitura, direcao)
        # so entram as razoes das camadas que sustentam ESTA direcao: uma
        # camada neutra explicando que tem poucos candles nao e' justificativa
        vies_alvo = avaliacao.vies
        razoes = tuple(avaliacao.motivos) + tuple(
            c.razoes[0] for c in leitura.camadas if c.vies is vies_alvo and c.razoes
        )
        return Opportunity(
            symbol=leitura.symbol,
            instante=leitura.instante,
            direcao=direcao,
            regra=avaliacao.regra.nome,
            leitura=leitura,
            confianca=avaliacao.confianca,
            razoes=razoes,
            invalidacao=self._invalidacao(leitura, direcao, niveis),
            niveis=niveis,
        )

    def _niveis(self, leitura: LeituraMultiTimeframe, direcao: Direction) -> dict:
        """Precos de REFERENCIA - quem dimensiona e' o Risk Manager."""
        setup = leitura.camada("setup")
        trigger = leitura.camada("trigger")
        preco = None
        if trigger is not None:
            preco = trigger.detalhes.get("preco")
        if preco is None and setup is not None:
            preco = setup.detalhes.get("preco")
        if preco is None:
            return {}

        atr = (setup.detalhes.get("atr") if setup else None) or preco * 0.005
        cfg = self.cfg_leitura
        if direcao is Direction.LONG:
            apoio = (setup.detalhes.get("suporte") if setup else None)
            stop = min(apoio, preco - cfg.stop_atr * atr) if apoio else preco - cfg.stop_atr * atr
            alvo = preco + cfg.alvo_em_r * (preco - stop)
        else:
            apoio = (setup.detalhes.get("resistencia") if setup else None)
            stop = max(apoio, preco + cfg.stop_atr * atr) if apoio else preco + cfg.stop_atr * atr
            alvo = preco - cfg.alvo_em_r * (stop - preco)
        return {"entrada_referencia": preco, "stop_referencia": stop,
                "alvo_referencia": alvo, "atr": atr}

    def _invalidacao(self, leitura: LeituraMultiTimeframe, direcao: Direction, niveis: dict) -> str:
        partes = []
        if "stop_referencia" in niveis:
            partes.append(f"perder {formata_dinheiro(niveis['stop_referencia'])}")
        trend = leitura.camada("trend")
        if trend is not None:
            lado = "de alta" if direcao is Direction.LONG else "de baixa"
            partes.append(f"a tendencia de {trend.timeframe} deixar de ser {lado}")
        setup = leitura.camada("setup")
        if setup is not None:
            partes.append(f"o setup de {setup.timeframe} desmanchar")
        return "; ".join(partes) if partes else "-"

    # ------------------------------------------------------------------
    def alimentar(self, serie_base: Series) -> MTFEngine:
        """Atalho: monta o motor de alinhamento com a configuracao deste engine."""
        return MTFEngine(self.config, symbol=serie_base.symbol).alimentar(serie_base)
