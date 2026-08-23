"""As regras: so ha Opportunity quando a combinacao inteira fecha."""

from __future__ import annotations

import pytest

from cashinho.core.confluencia import (
    PULLBACK_A_FAVOR,
    REGRAS_PADRAO,
    ROMPIMENTO_COM_CONTEXTO,
    ContextState,
    RegraOportunidade,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
)
from cashinho.models import Direction

from .factories import leitura


def test_o_exemplo_do_enunciado_fecha_a_regra():
    """60m bullish, 15m bullish, 5m pullback, 1m breakout_with_volume."""
    a = PULLBACK_A_FAVOR.avaliar(
        leitura(
            context=ContextState.BULLISH,
            trend=TrendState.BULLISH,
            setup=SetupState.PULLBACK,
            trigger=TriggerState.BREAKOUT_WITH_VOLUME,
        )
    )

    assert a.satisfeita is True
    assert a.vies is Vies.BULLISH
    assert a.falhas == ()


def test_o_espelho_para_baixo_tambem_fecha():
    a = PULLBACK_A_FAVOR.avaliar(
        leitura(
            context=ContextState.BEARISH, trend=TrendState.BEARISH,
            setup=SetupState.PULLBACK, trigger=TriggerState.BREAKOUT_WITH_VOLUME,
            vies_setup=Vies.BEARISH, vies_trigger=Vies.BEARISH,
        )
    )

    assert a.satisfeita is True
    assert a.vies is Vies.BEARISH


@pytest.mark.parametrize(
    "campos,papel",
    [
        ({"context": ContextState.NEUTRAL}, "context"),
        ({"trend": TrendState.SIDEWAYS}, "trend"),
        ({"setup": SetupState.NONE}, "setup"),
        ({"trigger": TriggerState.NONE}, "trigger"),
    ],
)
def test_basta_uma_camada_fora_para_nao_haver_oportunidade(campos, papel):
    a = PULLBACK_A_FAVOR.avaliar(leitura(**campos))

    assert a.satisfeita is False
    assert papel in [c.papel for c in a.falhas]


def test_camada_ausente_reprova_a_regra_que_a_exige():
    a = PULLBACK_A_FAVOR.avaliar(leitura(context=None))

    assert a.satisfeita is False
    falha = next(c for c in a.falhas if c.papel == "context")
    assert falha.obtido is None
    assert falha.observacao == "camada ausente"


def test_camadas_apontando_para_lados_diferentes_reprovam():
    a = PULLBACK_A_FAVOR.avaliar(
        leitura(context=ContextState.BULLISH, trend=TrendState.BEARISH)
    )

    assert a.satisfeita is False
    assert "alinhamento" in [c.papel for c in a.falhas]


def test_setup_e_gatilho_opostos_nunca_passam():
    """Invariante: o gatilho e' o que entra na operacao - nao pode ir ao contrario."""
    regra = RegraOportunidade(
        nome="teste sem alinhamento",
        setup=(SetupState.FAILED_BREAKOUT,),
        trigger=(TriggerState.BREAKOUT_WITH_VOLUME,),
        exigir_vies_alinhado=False,  # mesmo desligando o alinhamento geral
    )
    a = regra.avaliar(
        leitura(setup=SetupState.FAILED_BREAKOUT, trigger=TriggerState.BREAKOUT_WITH_VOLUME,
                vies_setup=Vies.BEARISH, vies_trigger=Vies.BULLISH)
    )

    assert a.satisfeita is False
    coerencia = next(c for c in a.falhas if c.papel == "coerencia")
    assert "lado oposto" in coerencia.observacao


def test_setup_e_gatilho_no_mesmo_lado_passam_na_coerencia():
    regra = RegraOportunidade(
        nome="teste", setup=(SetupState.FAILED_BREAKOUT,),
        trigger=(TriggerState.REJECTION_WICK,), exigir_vies_alinhado=False,
    )
    a = regra.avaliar(
        leitura(setup=SetupState.FAILED_BREAKOUT, trigger=TriggerState.REJECTION_WICK,
                vies_setup=Vies.BEARISH, vies_trigger=Vies.BEARISH)
    )

    assert a.satisfeita is True
    assert a.vies is Vies.BEARISH


def test_leitura_velha_demais_reprova():
    regra = RegraOportunidade(
        nome="contexto fresco",
        context=(ContextState.BULLISH,),
        trigger=(TriggerState.BREAKOUT_WITH_VOLUME,),
        idade_maxima_minutos={"context": 30},
    )
    a = regra.avaliar(leitura(idade_context_min=45))

    assert a.satisfeita is False
    falha = next(c for c in a.falhas if c.papel == "context")
    assert "45 min atras" in falha.observacao


def test_leitura_dentro_do_prazo_passa():
    regra = RegraOportunidade(
        nome="contexto fresco", context=(ContextState.BULLISH,),
        trigger=(TriggerState.BREAKOUT_WITH_VOLUME,), idade_maxima_minutos={"context": 60},
    )
    assert regra.avaliar(leitura(idade_context_min=45)).satisfeita is True


def test_confianca_minima_e_respeitada():
    fraca = leitura(forca=0.2)

    assert PULLBACK_A_FAVOR.avaliar(fraca).satisfeita is False
    assert "confianca" in [c.papel for c in PULLBACK_A_FAVOR.avaliar(fraca).falhas]


def test_regra_pode_travar_a_direcao():
    so_compra = RegraOportunidade(
        nome="so compra", context=(ContextState.BULLISH, ContextState.BEARISH),
        trigger=(TriggerState.BREAKOUT_WITH_VOLUME,), direcao=Direction.LONG,
    )
    de_baixa = leitura(context=ContextState.BEARISH, trend=TrendState.BEARISH,
                       vies_setup=Vies.BEARISH, vies_trigger=Vies.BEARISH)

    assert so_compra.avaliar(de_baixa).satisfeita is False
    assert so_compra.avaliar(leitura()).satisfeita is True


def test_regra_totalmente_customizada_funciona():
    minha = RegraOportunidade(
        nome="meu setup",
        context=(ContextState.NEUTRAL,),
        setup=(SetupState.RANGE_EDGE,),
        trigger=(TriggerState.REJECTION_WICK,),
        exigir_vies_alinhado=True,
        confianca_minima=0.0,
    )
    a = minha.avaliar(
        leitura(context=ContextState.NEUTRAL, trend=TrendState.SIDEWAYS,
                setup=SetupState.RANGE_EDGE, trigger=TriggerState.REJECTION_WICK)
    )

    assert a.satisfeita is True


def test_checagens_explicam_o_que_faltou():
    a = PULLBACK_A_FAVOR.avaliar(leitura(setup=SetupState.BREAKOUT))
    falha = next(c for c in a.falhas if c.papel == "setup")

    assert falha.obtido == "breakout"
    assert "pullback" in falha.esperado
    assert a.para_dict()["satisfeita"] is False


def test_regras_padrao_cobrem_pullback_rompimento_e_reversao():
    nomes = [r.nome for r in REGRAS_PADRAO]

    assert "pullback a favor da tendencia" in nomes
    assert "rompimento com contexto" in nomes
    assert "reversao de falso rompimento" in nomes


def test_rompimento_precisa_de_setup_de_rompimento():
    assert ROMPIMENTO_COM_CONTEXTO.avaliar(leitura(setup=SetupState.BREAKOUT)).satisfeita is True
    assert ROMPIMENTO_COM_CONTEXTO.avaliar(leitura(setup=SetupState.PULLBACK)).satisfeita is False
