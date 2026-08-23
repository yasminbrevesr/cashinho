"""Adaptador: o Multi-Timeframe Engine como uma Strategy.

Assim a confluencia entra em tudo o que ja existe - tela Analise, Risk
Manager, backtest e comparacao de timeframes - sem que nenhuma dessas pecas
precise conhecer o engine.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..strategy.base import Strategy, registrar
from ..strategy.context import StrategyContext
from ..strategy.models import Action, Factor, Signal
from .engine import MultiTimeframeEngine
from .estados import Vies
from .modelos import LeituraMultiTimeframe
from .regras import AvaliacaoRegra

AVISO = (
    "confluencia multi-timeframe com regras simples - sem otimizacao nem backtest "
    "validado; nao e' uma estrategia final nem recomendacao"
)


class EstrategiaConfluencia(Strategy):
    """Emite BUY/SELL apenas quando uma regra de confluencia fecha."""

    nome = "confluencia-mtf"
    descricao = "contexto 60m, tendencia 15m, setup 5m e gatilho 1m com regras configuraveis"
    timeframe_preferido = "5m"
    experimental = True
    aviso = AVISO

    def __init__(self, engine: Optional[MultiTimeframeEngine] = None):
        self.engine = engine or MultiTimeframeEngine()

    def avaliar(self, contexto: StrategyContext) -> Signal:
        vista = contexto.extras.get("vista")
        if vista is None:
            return self.sinal_vazio(
                contexto,
                "esta estrategia precisa da vista multi-timeframe no contexto "
                "(use cashinho.core.strategy.de_vista)",
            )

        resultado = self.engine.avaliar(vista, contexto.symbol)
        leitura = resultado.leitura
        candidata = resultado.candidata
        fatores = _fatores(leitura, resultado.avaliacoes)

        if candidata is None:
            return Signal(
                symbol=contexto.symbol,
                timestamp=leitura.instante,
                timeframe=self._timeframe(leitura),
                action=Action.WAIT if leitura.completa else Action.NONE,
                setup=_setup_textual(leitura),
                confidence=_confianca_parcial(resultado.avaliacoes),
                reasons=_motivos_da_espera(resultado.avaliacoes, leitura),
                invalidation="-",
                strategy=self.nome,
                factors=fatores,
                experimental=True,
                aviso=AVISO,
                extras={"multitimeframe": leitura, "avaliacoes": resultado.avaliacoes},
            )

        action = Action.BUY if candidata.direcao.value == "COMPRA" else Action.SELL
        return Signal(
            symbol=contexto.symbol,
            timestamp=candidata.instante,
            timeframe=self._timeframe(leitura),
            action=action,
            setup=f"{candidata.regra} ({candidata.resumo_das_camadas})",
            confidence=candidata.confianca,
            reasons=candidata.razoes,
            invalidation=candidata.invalidacao,
            strategy=self.nome,
            vies=candidata.direcao,
            factors=fatores,
            niveis=candidata.niveis,
            experimental=True,
            aviso=AVISO,
            extras={
                "multitimeframe": leitura,
                "avaliacoes": resultado.avaliacoes,
                "candidata": candidata,
            },
        )

    def _timeframe(self, leitura: LeituraMultiTimeframe) -> str:
        setup = leitura.camada("setup")
        return setup.timeframe if setup else self.timeframe_preferido


def _fatores(leitura: LeituraMultiTimeframe, avaliacoes: Sequence[AvaliacaoRegra]) -> tuple[Factor, ...]:
    """Cada camada vira um fator, a favor ou contra o vies dominante."""
    alinhado = leitura.vies_alinhado()
    fatores = []
    for c in leitura.camadas:
        if alinhado is None:
            favoravel = None if c.vies is Vies.NEUTRAL else True
        else:
            favoravel = None if c.vies is Vies.NEUTRAL else (c.vies is alinhado)
        fatores.append(
            Factor(
                nome=f"{c.papel} ({c.timeframe})",
                favoravel=favoravel,
                detalhe=f"{c.valor}: {c.razoes[0] if c.razoes else '-'}",
                peso=1.0,
                obrigatorio=True,
            )
        )
    for papel in leitura.faltando:
        fatores.append(
            Factor(nome=papel, favoravel=False, detalhe="sem candle fechado ainda",
                   peso=1.0, obrigatorio=True)
        )
    return tuple(fatores)


def _setup_textual(leitura: LeituraMultiTimeframe) -> str:
    setup = leitura.camada("setup")
    if setup is None:
        return "camadas incompletas"
    return f"{setup.timeframe}: {setup.valor}"


def _confianca_parcial(avaliacoes: Sequence[AvaliacaoRegra]) -> float:
    """A regra que chegou mais perto - so para dar nocao de quao longe esta."""
    if not avaliacoes:
        return 0.0
    melhor = max(avaliacoes, key=lambda a: sum(1 for c in a.checagens if c.ok) / max(len(a.checagens), 1))
    atendidas = sum(1 for c in melhor.checagens if c.ok)
    return round(atendidas / max(len(melhor.checagens), 1), 3)


def _motivos_da_espera(avaliacoes: Sequence[AvaliacaoRegra],
                       leitura: LeituraMultiTimeframe) -> tuple[str, ...]:
    if leitura.faltando:
        return tuple(f"camada {p} ainda sem candle fechado" for p in leitura.faltando)
    motivos = []
    for a in avaliacoes:
        if a.falhas:
            falha = a.falhas[0]
            motivos.append(
                f"{a.regra.nome}: {falha.papel} = {falha.obtido or '-'} "
                f"(esperado {'/'.join(falha.esperado)})"
            )
    return tuple(motivos)


registrar(EstrategiaConfluencia.nome, EstrategiaConfluencia)
