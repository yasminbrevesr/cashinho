"""Score explicavel, amostra e a separacao entre fit e evidencia."""

from __future__ import annotations

import pytest

from cashinho.core.advisor import (
    AMOSTRA_PLENA,
    Estatistica,
    NivelDeConfianca,
    PesosAdvisor,
    PesosInvalidosError,
    calcular,
    calcular_confianca,
    medir,
)
from cashinho.core.advisor.medidas import Medida, MedidasDoTimeframe
from cashinho.core.structure.models import Regime

from .factories import estatistica, lateral_ruidosa, tendencia


def medidas(**campos) -> MedidasDoTimeframe:
    base = dict(
        timeframe="5m", candles=200,
        eficiencia=Medida(0.45, "direcional"),
        volatilidade_pct=Medida(0.6, "ATR 0,6%"),
        volume_relativo=Medida(1.1, "volume normal"),
        spread_relativo=Medida(0.04, "spread baixo"),
        regime=Regime.ALTA, forca_da_tendencia=0.8,
        rompimentos=8, falsos_rompimentos=1, pivos=16,
        estabilidade=Medida(0.8, "estavel"),
    )
    base.update(campos)
    return MedidasDoTimeframe(**base)


# --- os seis componentes ---------------------------------------------------


def test_o_score_tem_os_seis_componentes():
    s = calcular(medidas(), Regime.ALTA, estatistica())

    assert {c.chave for c in s.componentes} == {
        "regime", "estrutura", "ruido", "liquidez", "performance", "estabilidade"}


def test_todo_componente_traz_a_leitura_que_o_explica():
    for c in calcular(medidas(), Regime.ALTA, estatistica()).componentes:
        assert c.leitura


def test_o_score_e_reproduzivel():
    a = calcular(medidas(), Regime.ALTA, estatistica())
    b = calcular(medidas(), Regime.ALTA, estatistica())

    assert a.total == b.total
    assert [c.nota for c in a.componentes] == [c.nota for c in b.componentes]


def test_os_pesos_sao_configuraveis():
    so_ruido = PesosAdvisor(regime=0, estrutura=0, ruido=1, liquidez=0,
                            performance=0, estabilidade=0)
    s = calcular(medidas(), Regime.ALTA, estatistica(), so_ruido)
    ruido = s.componente("ruido")

    assert s.total == pytest.approx(ruido.nota, abs=0.1)


def test_pesos_invalidos_sao_recusados():
    with pytest.raises(PesosInvalidosError):
        PesosAdvisor(regime=-1)
    with pytest.raises(PesosInvalidosError):
        PesosAdvisor(regime=0, estrutura=0, ruido=0, liquidez=0,
                     performance=0, estabilidade=0)


def test_alinhamento_com_o_contexto_vale_mais_que_contrariar():
    alinhado = calcular(medidas(regime=Regime.ALTA), Regime.ALTA)
    contra = calcular(medidas(regime=Regime.ALTA), Regime.BAIXA)

    assert alinhado.componente("regime").nota > contra.componente("regime").nota


def test_ruido_alto_derruba_a_nota():
    limpo = calcular(medidas(eficiencia=Medida(0.6, "direcional")))
    sujo = calcular(medidas(eficiencia=Medida(0.05, "muito ruido")))

    assert limpo.componente("ruido").nota > sujo.componente("ruido").nota


def test_falso_rompimento_derruba_a_estrutura():
    limpa = calcular(medidas(rompimentos=10, falsos_rompimentos=0))
    suja = calcular(medidas(rompimentos=2, falsos_rompimentos=8))

    assert limpa.componente("estrutura").nota > suja.componente("estrutura").nota


def test_densidade_de_pivo_alta_nao_vira_boa_estrutura():
    """Contar pivos premiaria o timeframe mais ruidoso."""
    equilibrada = calcular(medidas(pivos=16, candles=200))
    excessiva = calcular(medidas(pivos=90, candles=200))

    assert equilibrada.componente("estrutura").nota > excessiva.componente("estrutura").nota


# --- metrica ausente: indisponivel, nunca zero --------------------------------


def test_componente_sem_dado_fica_indisponivel_e_nao_zero():
    s = calcular(medidas(spread_relativo=Medida(None, "sem book"),
                         volume_relativo=Medida(None, "sem volume")))
    liquidez = s.componente("liquidez")

    assert liquidez.nota is None
    assert liquidez.disponivel is False
    assert "Liquidez" in s.indisponiveis


def test_sem_historico_a_performance_fica_indisponivel():
    s = calcular(medidas(), Regime.ALTA, estatistica=None)

    assert s.componente("performance").nota is None
    assert s.statistical_evidence is None


def test_componente_indisponivel_nao_entra_na_media():
    com = calcular(medidas(), Regime.ALTA, estatistica(expectancy=0.0))
    sem = calcular(medidas(), Regime.ALTA, None)

    assert com.total != sem.total       # a performance zerada puxa; ausente, nao


# --- fit x evidencia -----------------------------------------------------------


def test_market_fit_nao_inclui_performance():
    """Uma manha boa nao pode virar conclusao estatistica."""
    com = calcular(medidas(), Regime.ALTA, estatistica(trades=200, expectancy=1.0))
    sem = calcular(medidas(), Regime.ALTA, None)

    assert com.market_fit == sem.market_fit


def test_evidencia_alta_com_fit_baixo_e_possivel():
    fraco = calcular(medidas(eficiencia=Medida(0.05, "ruido"), pivos=90),
                     Regime.BAIXA, estatistica(trades=100, expectancy=0.9))

    assert fraco.statistical_evidence is not None
    assert fraco.statistical_evidence > fraco.market_fit


# --- amostra ---------------------------------------------------------------------


def test_uma_operacao_sortuda_nao_vence_trinta_medianas():
    """+4R em 1 trade contra +0,45R em 30."""
    sortuda = Estatistica(trades=1, expectancy=4.0)
    consistente = Estatistica(trades=30, expectancy=0.45)

    assert sortuda.nota < consistente.nota


def test_o_peso_da_amostra_cresce_e_satura():
    assert Estatistica(trades=1, expectancy=1.0).peso_da_amostra < 0.2
    assert Estatistica(trades=AMOSTRA_PLENA, expectancy=1.0).peso_da_amostra == 1.0
    assert Estatistica(trades=500, expectancy=1.0).peso_da_amostra == 1.0


def test_sem_trades_nao_ha_estatistica():
    assert Estatistica().disponivel is False
    assert Estatistica().nota is None


def test_poucos_candles_derrubam_a_confianca():
    muitos = calcular_confianca(400, estatistica(), ())
    poucos = calcular_confianca(40, estatistica(), ())

    assert muitos.valor > poucos.valor


def test_menos_de_trinta_candles_e_insuficiente():
    c = calcular_confianca(10, estatistica(), ())

    assert c.nivel is NivelDeConfianca.INSUFICIENTE
    assert c.recomenda is False


def test_sem_historico_a_confianca_e_limitada():
    com = calcular_confianca(400, estatistica(trades=50), ())
    sem = calcular_confianca(400, None, ())

    assert sem.valor < com.valor
    assert any("sem evidencia estatistica" in m for m in sem.motivos)


def test_metrica_ausente_reduz_a_confianca():
    completa = calcular_confianca(400, estatistica(), ())
    faltando = calcular_confianca(400, estatistica(), ("Liquidez", "Estrutura"))

    assert faltando.valor < completa.valor
    assert any("sem dado para" in m for m in faltando.motivos)


def test_vantagem_pequena_reduz_a_confianca():
    folgada = calcular_confianca(400, estatistica(), (), vantagem=20.0)
    apertada = calcular_confianca(400, estatistica(), (), vantagem=1.0)

    assert apertada.valor < folgada.valor
    assert any("vantagem de apenas" in m for m in apertada.motivos)


def test_a_confianca_sempre_diz_por_que():
    c = calcular_confianca(50, Estatistica(trades=2, expectancy=1.0), ("Liquidez",))

    assert c.motivos
