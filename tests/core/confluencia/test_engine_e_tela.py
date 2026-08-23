"""O engine ponta a ponta e a secao ANALISE MULTI-TIMEFRAME."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.confluencia import (
    ContextState,
    EstrategiaConfluencia,
    MultiTimeframeEngine,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
    linha_resumo,
    secao_multitimeframe,
)
from cashinho.core.confluencia.regras import PULLBACK_A_FAVOR
from cashinho.core.strategy import Action, de_vista, tela_analise
from cashinho.models import Direction

from .factories import ABERTURA, leitura, motor, serie_alta

ENGINE = MultiTimeframeEngine()


# --- engine ---------------------------------------------------------------------


def test_avaliar_devolve_leitura_avaliacoes_e_oportunidade():
    vista = motor(serie_alta()).em(ABERTURA + timedelta(minutes=250))
    resultado = ENGINE.avaliar(vista, "PETR4")

    assert resultado.leitura.instante == vista.instante
    assert len(resultado.avaliacoes) == len(ENGINE.regras)
    assert resultado.tem_oportunidade == (resultado.oportunidade is not None)


def test_sem_regra_satisfeita_nao_ha_oportunidade():
    vista = motor(serie_alta()).em(ABERTURA + timedelta(minutes=60))
    resultado = ENGINE.avaliar(vista, "PETR4")

    if not resultado.satisfeitas:
        assert resultado.oportunidade is None


def test_oportunidade_traz_niveis_coerentes():
    """Compra: stop abaixo da entrada e alvo acima. Venda: espelhado."""
    engine = MultiTimeframeEngine()
    m = motor(serie_alta())
    encontrada = None
    for vista in m.replay():
        resultado = engine.avaliar(vista, "PETR4")
        if resultado.oportunidade is not None:
            encontrada = resultado.oportunidade
            break

    if encontrada is not None:
        n = encontrada.niveis
        if encontrada.direcao is Direction.LONG:
            assert n["stop_referencia"] < n["entrada_referencia"] < n["alvo_referencia"]
        else:
            assert n["alvo_referencia"] < n["entrada_referencia"] < n["stop_referencia"]


def test_oportunidade_nao_tem_quantidade():
    """Dimensionar e' do Risk Manager - a oportunidade so descreve."""
    from cashinho.core.confluencia.modelos import Opportunity
    import dataclasses

    campos = {f.name for f in dataclasses.fields(Opportunity)}
    assert not campos & {"quantidade", "position_size", "ordem"}


def test_resultado_serializa_para_a_interface():
    vista = motor(serie_alta()).em(ABERTURA + timedelta(minutes=250))
    dados = ENGINE.avaliar(vista, "PETR4").para_dict()
    texto = json.dumps(dados)

    assert dados["leitura"]["symbol"] == "PETR4"
    assert len(dados["avaliacoes"]) == 3
    assert '"camadas"' in texto


def test_papeis_saem_do_maior_para_o_menor_timeframe():
    assert ENGINE.papeis == ["context", "trend", "setup", "trigger"]


# --- estrategia adaptadora ----------------------------------------------------------


def test_estrategia_sem_vista_no_contexto_avisa():
    from cashinho.core.strategy import StrategyContext

    sinal = EstrategiaConfluencia().avaliar(
        StrategyContext("PETR4", serie_alta().tail(100))
    )

    assert sinal.action is Action.NONE
    assert "vista multi-timeframe" in sinal.reasons[0]


def test_estrategia_anexa_a_leitura_no_sinal():
    m = motor(serie_alta())
    vista = m.em(ABERTURA + timedelta(minutes=250))
    sinal = EstrategiaConfluencia().avaliar(
        de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
    )

    assert "multitimeframe" in sinal.extras
    assert len(sinal.extras["avaliacoes"]) == 3


def test_sinal_acionavel_so_com_oportunidade():
    engine = MultiTimeframeEngine()
    estrategia = EstrategiaConfluencia(engine)
    m = motor(serie_alta())

    for vista in list(m.replay())[60::30]:
        if len(vista.fechados("5m")) == 0:
            continue
        sinal = estrategia.avaliar(de_vista(vista, "PETR4", papel_setup="setup",
                                            papel_tendencia="trend"))
        tem_oportunidade = sinal.extras.get("oportunidade") is not None
        assert sinal.action.acionavel == tem_oportunidade


def test_estrategia_esta_registrada():
    from cashinho.core.strategy import disponiveis, obter

    assert "confluencia-mtf" in disponiveis()
    assert isinstance(obter("confluencia-mtf"), EstrategiaConfluencia)


# --- secao da tela -------------------------------------------------------------------


LEITURA = leitura()
AVALIACOES = [r.avaliar(LEITURA) for r in MultiTimeframeEngine().regras]


def test_secao_mostra_as_quatro_camadas():
    texto = secao_multitimeframe(LEITURA)

    assert "ANALISE MULTI-TIMEFRAME" in texto
    for papel in ("context", "trend", "setup", "trigger"):
        assert papel in texto
    for tf in ("60m", "15m", "5m", "1m"):
        assert tf in texto


def test_secao_mostra_o_estado_de_cada_periodo():
    texto = secao_multitimeframe(LEITURA)

    assert "bullish" in texto
    assert "pullback" in texto
    assert "breakout_with_volume" in texto


def test_secao_mostra_quando_cada_leitura_fechou_e_a_idade():
    """Um contexto de 60m lido as 12:37 e' do candle das 12:00 - isso precisa aparecer."""
    texto = secao_multitimeframe(LEITURA)

    assert "fechou" in texto and "idade" in texto
    assert "37 min" in texto
    assert "agora" in texto  # o gatilho


def test_secao_mostra_o_alinhamento():
    alinhada = secao_multitimeframe(LEITURA)
    desalinhada = secao_multitimeframe(
        leitura(context=ContextState.BEARISH, vies_setup=Vies.BULLISH)
    )

    assert "apontam para bullish" in alinhada
    assert "desacordo" in desalinhada


def test_secao_lista_as_regras_com_o_que_faltou():
    texto = secao_multitimeframe(LEITURA, AVALIACOES)

    assert "REGRAS DE CONFLUENCIA" in texto
    assert "✔ pullback a favor da tendencia" in texto
    assert "esperado" in texto  # explica a regra que nao fechou


def test_secao_avisa_camada_ausente():
    texto = secao_multitimeframe(leitura(context=None))

    assert "sem candle fechado ainda" in texto


def test_secao_entra_na_tela_analise():
    m = motor(serie_alta())
    vista = m.em(ABERTURA + timedelta(minutes=250))
    sinal = EstrategiaConfluencia().avaliar(
        de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
    )
    texto = tela_analise(sinal)

    assert "ANALISE MULTI-TIMEFRAME" in texto
    assert "JUSTIFICATIVAS" in texto  # a tela original continua inteira


def test_tela_sem_leitura_nao_mostra_a_secao():
    from cashinho.core.strategy import BaselineTendenciaVolumeATR, StrategyContext

    sinal = BaselineTendenciaVolumeATR().avaliar(
        StrategyContext("PETR4", serie_alta().tail(120))
    )
    assert "ANALISE MULTI-TIMEFRAME" not in tela_analise(sinal)


def test_linha_resumo_cabe_em_uma_linha():
    linha = linha_resumo(LEITURA)

    assert "\n" not in linha
    assert "60m:bullish" in linha and "1m:breakout_with_volume" in linha


def test_cores_sao_opcionais():
    assert "\033[" not in secao_multitimeframe(LEITURA, AVALIACOES, cores=False)
    assert "\033[" in secao_multitimeframe(LEITURA, AVALIACOES, cores=True)
