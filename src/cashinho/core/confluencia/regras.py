"""Regras de confluencia: quando as quatro camadas autorizam uma Opportunity.

Uma regra e' uma lista de estados aceitos por papel. Ela so e' satisfeita
quando TODOS os papeis que ela exige batem - nao existe "quase". O resultado
da avaliacao guarda cada checagem, inclusive as que falharam, para a tela
poder explicar por que nao houve oportunidade.

O exemplo do enunciado e' a primeira regra do conjunto padrao::

    60m: context = bullish
    15m: trend   = bullish
     5m: setup   = pullback
     1m: trigger = breakout_with_volume
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ...models import Direction
from .estados import ContextState, SetupState, TrendState, TriggerState, Vies
from .modelos import Camada, LeituraMultiTimeframe


@dataclass(frozen=True)
class Checagem:
    """Uma exigencia da regra, com o que se pediu e o que se leu."""

    papel: str
    esperado: tuple[str, ...]
    obtido: Optional[str]
    ok: bool
    observacao: str = ""

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return f"{self.papel}: {self.obtido or '-'} ({'ok' if self.ok else 'esperado ' + '/'.join(self.esperado)})"


@dataclass(frozen=True)
class AvaliacaoRegra:
    regra: "RegraOportunidade"
    satisfeita: bool
    checagens: tuple[Checagem, ...]
    vies: Optional[Vies] = None
    confianca: float = 0.0
    motivos: tuple[str, ...] = ()

    @property
    def falhas(self) -> tuple[Checagem, ...]:
        return tuple(c for c in self.checagens if not c.ok)

    def para_dict(self) -> dict:
        return {
            "regra": self.regra.nome,
            "satisfeita": self.satisfeita,
            "vies": self.vies.value if self.vies else None,
            "confianca": round(self.confianca, 3),
            "checagens": [
                {"papel": c.papel, "esperado": list(c.esperado), "obtido": c.obtido,
                 "ok": c.ok, "observacao": c.observacao}
                for c in self.checagens
            ],
        }


@dataclass(frozen=True)
class RegraOportunidade:
    """Uma combinacao de estados que autoriza uma oportunidade."""

    nome: str
    context: tuple[ContextState, ...] = ()
    trend: tuple[TrendState, ...] = ()
    setup: tuple[SetupState, ...] = ()
    trigger: tuple[TriggerState, ...] = ()
    exigir_vies_alinhado: bool = True
    direcao: Optional[Direction] = None  # trava a regra em um lado
    idade_maxima_minutos: dict = field(default_factory=dict)  # por papel
    confianca_minima: float = 0.0
    descricao: str = ""

    @property
    def exigencias(self) -> dict:
        return {
            "context": tuple(e.value for e in self.context),
            "trend": tuple(e.value for e in self.trend),
            "setup": tuple(e.value for e in self.setup),
            "trigger": tuple(e.value for e in self.trigger),
        }

    # ------------------------------------------------------------------
    def avaliar(self, leitura: LeituraMultiTimeframe) -> AvaliacaoRegra:
        checagens: list[Checagem] = []
        motivos: list[str] = []

        for papel, esperados in self.exigencias.items():
            if not esperados:
                continue
            camada = leitura.camada(papel)
            if camada is None:
                checagens.append(Checagem(papel, esperados, None, False, "camada ausente"))
                continue
            ok = camada.valor in esperados
            observacao = ""
            if ok:
                limite = self.idade_maxima_minutos.get(papel)
                if limite is not None and camada.idade_minutos > limite:
                    ok = False
                    observacao = (
                        f"leitura de {camada.idade_minutos:.0f} min atras, acima do "
                        f"limite de {limite:.0f} min"
                    )
                else:
                    motivos.append(f"{camada.timeframe}: {papel} = {camada.valor}")
            checagens.append(Checagem(papel, esperados, camada.valor, ok, observacao))

        vies = self._vies(leitura, checagens)

        # invariante que nenhuma regra pode desligar: o gatilho e' o que
        # coloca a operacao na rua, entao ele nao pode apontar para o lado
        # oposto do setup. Sem isso, uma regra com exigir_vies_alinhado=False
        # aceitaria "falso rompimento de alta" com "gatilho de compra".
        coerencia = self._coerencia_setup_trigger(leitura)
        if coerencia is not None:
            checagens.append(coerencia)

        if self.exigir_vies_alinhado:
            alinhado = self._vies_alinhado(leitura)
            ok = alinhado is not None
            checagens.append(
                Checagem(
                    "alinhamento", ("mesmo vies em todas as camadas",),
                    alinhado.value if alinhado else "camadas apontando para lados diferentes",
                    ok,
                )
            )
            if ok:
                vies = alinhado
                motivos.append(f"as quatro camadas apontam para {alinhado.value}")

        if self.direcao is not None and vies is not None:
            esperado = Vies.de_direcao(self.direcao)
            ok = vies is esperado
            checagens.append(Checagem("direcao", (esperado.value,), vies.value, ok))

        confianca = self._confianca(leitura)
        if confianca < self.confianca_minima:
            checagens.append(
                Checagem(
                    "confianca", (f">= {self.confianca_minima:.2f}",), f"{confianca:.2f}", False,
                )
            )

        satisfeita = all(c.ok for c in checagens) and vies not in (None, Vies.NEUTRAL)
        return AvaliacaoRegra(
            regra=self,
            satisfeita=satisfeita,
            checagens=tuple(checagens),
            vies=vies,
            confianca=confianca,
            motivos=tuple(motivos),
        )

    # ------------------------------------------------------------------
    def _vies(self, leitura: LeituraMultiTimeframe, checagens: Sequence[Checagem]) -> Optional[Vies]:
        """O lado da operacao vem do gatilho; sem gatilho, do setup."""
        for papel in ("trigger", "setup", "trend", "context"):
            camada = leitura.camada(papel)
            if camada is not None and camada.vies is not Vies.NEUTRAL:
                return camada.vies
        return None

    def _coerencia_setup_trigger(self, leitura: LeituraMultiTimeframe) -> Optional[Checagem]:
        """Setup e gatilho precisam apontar para o mesmo lado, sempre."""
        if not (self.exigencias["setup"] and self.exigencias["trigger"]):
            return None
        setup = leitura.camada("setup")
        trigger = leitura.camada("trigger")
        if setup is None or trigger is None:
            return None
        if setup.vies is Vies.NEUTRAL or trigger.vies is Vies.NEUTRAL:
            return None
        ok = setup.vies is trigger.vies
        return Checagem(
            "coerencia", ("setup e trigger no mesmo lado",),
            f"setup {setup.vies.value} / trigger {trigger.vies.value}",
            ok,
            "" if ok else "o gatilho aponta para o lado oposto do setup",
        )

    def _vies_alinhado(self, leitura: LeituraMultiTimeframe) -> Optional[Vies]:
        """Todas as camadas exigidas pela regra apontando para o mesmo lado."""
        papeis = [p for p, e in self.exigencias.items() if e]
        vieses = set()
        for papel in papeis:
            camada = leitura.camada(papel)
            if camada is None:
                return None
            if camada.vies is not Vies.NEUTRAL:
                vieses.add(camada.vies)
        if len(vieses) == 1:
            return next(iter(vieses))
        return None

    def _confianca(self, leitura: LeituraMultiTimeframe) -> float:
        """Media das forcas das camadas que a regra exige."""
        papeis = [p for p, e in self.exigencias.items() if e]
        forcas = [leitura.camada(p).forca for p in papeis if leitura.camada(p) is not None]
        return round(sum(forcas) / len(forcas), 3) if forcas else 0.0

    def para_dict(self) -> dict:
        return {
            "nome": self.nome,
            "descricao": self.descricao,
            "exigencias": {k: list(v) for k, v in self.exigencias.items() if v},
            "exigir_vies_alinhado": self.exigir_vies_alinhado,
            "direcao": self.direcao.value if self.direcao else None,
            "idade_maxima_minutos": dict(self.idade_maxima_minutos),
            "confianca_minima": self.confianca_minima,
        }


# ---------------------------------------------------------------------------
# conjunto padrao
# ---------------------------------------------------------------------------

PULLBACK_A_FAVOR = RegraOportunidade(
    nome="pullback a favor da tendencia",
    descricao=(
        "contexto e tendencia no mesmo lado, correcao no timeframe de operacao e "
        "gatilho no candle rapido - o exemplo classico de confluencia"
    ),
    context=(ContextState.BULLISH, ContextState.BEARISH),
    trend=(TrendState.BULLISH, TrendState.BEARISH),
    setup=(SetupState.PULLBACK,),
    trigger=(TriggerState.BREAKOUT_WITH_VOLUME, TriggerState.MA_RECLAIM),
    exigir_vies_alinhado=True,
    confianca_minima=0.5,
)

ROMPIMENTO_COM_CONTEXTO = RegraOportunidade(
    nome="rompimento com contexto",
    descricao="rompimento de zona no timeframe de operacao, com contexto e tendencia a favor",
    context=(ContextState.BULLISH, ContextState.BEARISH),
    trend=(TrendState.BULLISH, TrendState.BEARISH),
    setup=(SetupState.BREAKOUT,),
    trigger=(TriggerState.BREAKOUT_WITH_VOLUME,),
    exigir_vies_alinhado=True,
    confianca_minima=0.5,
)

REVERSAO_DE_FALSO_ROMPIMENTO = RegraOportunidade(
    nome="reversao de falso rompimento",
    descricao=(
        "falso rompimento no timeframe de operacao com rejeicao no gatilho - "
        "opera contra o movimento que falhou, entao nao exige o contexto"
    ),
    trend=(TrendState.BULLISH, TrendState.BEARISH, TrendState.SIDEWAYS),
    setup=(SetupState.FAILED_BREAKOUT,),
    trigger=(TriggerState.REJECTION_WICK, TriggerState.BREAKOUT_WITH_VOLUME),
    # nao exige o contexto (ele nem esta nas exigencias), mas as camadas que
    # a regra usa precisam concordar entre si
    exigir_vies_alinhado=True,
    confianca_minima=0.4,
)

REGRAS_PADRAO: tuple[RegraOportunidade, ...] = (
    PULLBACK_A_FAVOR,
    ROMPIMENTO_COM_CONTEXTO,
    REVERSAO_DE_FALSO_ROMPIMENTO,
)
