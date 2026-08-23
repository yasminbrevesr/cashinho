"""O sistema de score: onze componentes, pesos configuraveis, nada opaco."""

from __future__ import annotations

import json

import pytest

from cashinho.core.confluencia.estados import (
    ContextState,
    SetupState,
    TrendState,
    TriggerState,
    Vies,
)
from cashinho.core.oportunidade.score import (
    AVALIADORES,
    NOMES,
    PESOS_PADRAO,
    PesosInvalidosError,
    PesosScore,
    calcular,
    nota_estrutura,
    nota_fibonacci,
    nota_gatilho,
    nota_medias,
    nota_momentum,
    nota_risco_retorno,
    nota_suporte_resistencia,
    nota_tendencia,
    nota_vwap,
    nota_volatilidade,
    nota_volume,
)
from cashinho.models import Direction

from .factories import (
    contexto,
    serie,
    serie_alta,
    serie_baixa,
    serie_com_swings_de_alta,
    serie_com_swings_de_baixa,
)


# ---------------------------------------------------------------------------
# os onze componentes existem e sao os pedidos
# ---------------------------------------------------------------------------


def test_os_onze_componentes_pedidos_estao_presentes():
    esperados = {
        "tendencia", "estrutura", "volume", "vwap", "medias", "momentum",
        "volatilidade", "suporte_resistencia", "fibonacci", "gatilho", "risco_retorno",
    }

    assert set(AVALIADORES) == esperados
    assert set(NOMES) == esperados
    assert len(esperados) == 11


def test_toda_nota_fica_entre_0_e_100():
    detalhado = calcular(contexto())

    for c in detalhado.componentes:
        assert 0.0 <= c.nota <= 100.0
    assert 0.0 <= detalhado.total <= 100.0


def test_todo_componente_explica_a_propria_nota():
    """Nao existe nota sem leitura - e' o que impede a caixa-preta."""
    for c in calcular(contexto()).componentes:
        assert c.leitura, f"{c.chave} nao explicou a nota"
        assert len(c.leitura) > 10


# ---------------------------------------------------------------------------
# componente a componente
# ---------------------------------------------------------------------------


def test_tendencia_premia_alinhamento_e_pune_contramao():
    a_favor = nota_tendencia(contexto(trend=TrendState.BULLISH, context=ContextState.BULLISH))
    contra = nota_tendencia(contexto(trend=TrendState.BEARISH, context=ContextState.BEARISH,
                                     vies=Vies.BEARISH))
    neutra = nota_tendencia(contexto(trend=TrendState.SIDEWAYS, context=ContextState.NEUTRAL))

    assert a_favor.nota > neutra.nota > contra.nota
    assert "a favor" in a_favor.leitura
    assert "CONTRA" in contra.leitura


def test_estrutura_segue_o_regime():
    subindo = serie_com_swings_de_alta()
    a_favor = nota_estrutura(contexto(serie_setup=subindo, direcao=Direction.LONG))
    contra = nota_estrutura(contexto(serie_setup=subindo, direcao=Direction.SHORT))

    assert a_favor.nota > contra.nota
    assert "a favor" in a_favor.leitura
    assert "contra" in contra.leitura


def test_alta_monotonica_sem_pivo_nao_vira_tendencia_estrutural():
    """Sem topo e fundo nao ha estrutura para ler - e a nota diz isso."""
    nota = nota_estrutura(contexto(serie_setup=serie_alta(), direcao=Direction.LONG))

    assert nota.nota == 40.0
    assert "lateral" in nota.leitura


def test_volume_cresce_com_o_volume_relativo():
    normal = serie_alta(n=60, timeframe="1m", minutos=1)
    forte = serie_alta(n=60, timeframe="1m", minutos=1,
                       volumes=[10_000.0] * 59 + [50_000.0])

    fraco = nota_volume(contexto(serie_trigger=normal))
    bom = nota_volume(contexto(serie_trigger=forte))

    assert bom.nota > fraco.nota
    assert "x a media" in bom.leitura


def test_vwap_pune_preco_do_lado_errado():
    ctx = contexto()
    ctx.vwap, ctx.vwap_sup, ctx.vwap_inf = 31.5, 31.8, 31.2  # preco 31,00 abaixo
    abaixo = nota_vwap(ctx)

    ctx2 = contexto()
    ctx2.vwap, ctx2.vwap_sup, ctx2.vwap_inf = 30.5, 31.4, 29.6  # preco acima e dentro
    acima = nota_vwap(ctx2)

    assert acima.nota > abaixo.nota
    assert "lado errado" in abaixo.leitura


def test_vwap_pune_preco_esticado_alem_da_banda():
    ctx = contexto()
    ctx.vwap, ctx.vwap_sup, ctx.vwap_inf = 30.0, 30.5, 29.5  # preco 31,00 alem da banda
    esticado = nota_vwap(ctx)

    assert 40 <= esticado.nota <= 70
    assert "esticado" in esticado.leitura


def test_medias_premiam_empilhamento():
    ctx = contexto(serie_setup=serie_alta())
    boa = nota_medias(ctx)

    ctx_ruim = contexto(serie_setup=serie_alta(), direcao=Direction.SHORT)
    ruim = nota_medias(ctx_ruim)

    assert boa.nota > ruim.nota


def test_momentum_pune_rsi_esticado():
    ctx = contexto()
    ctx.rsi, ctx.macd_hist = 62.0, 0.05
    ideal = nota_momentum(ctx)

    ctx2 = contexto()
    ctx2.rsi, ctx2.macd_hist = 85.0, 0.05
    esticado = nota_momentum(ctx2)

    assert ideal.nota > esticado.nota
    assert "esticado" in esticado.leitura


def test_momentum_considera_o_macd():
    ctx = contexto()
    ctx.rsi, ctx.macd_hist = 60.0, 0.05
    a_favor = nota_momentum(ctx)
    ctx.macd_hist = -0.05
    contra = nota_momentum(ctx)

    assert a_favor.nota > contra.nota


@pytest.mark.parametrize("atr_pct,esperado", [(0.05, "parado"), (5.0, "excessiva")])
def test_volatilidade_fora_da_faixa_tira_nota(atr_pct, esperado):
    ctx = contexto()
    ctx.atr_pct = atr_pct
    nota = nota_volatilidade(ctx)

    assert nota.nota < 30
    assert esperado in nota.leitura


def test_volatilidade_ideal_tira_nota_alta():
    ctx = contexto()
    ctx.atr_pct = 0.60
    assert nota_volatilidade(ctx).nota > 90


def test_suporte_resistencia_pune_alvo_dentro_da_parede():
    """Alvo do outro lado de uma resistencia colada: a operacao nao tem espaco."""
    ctx = contexto(entry=31.0, stop=30.5, target=40.0)  # alvo absurdo, longe
    nota = nota_suporte_resistencia(ctx)

    if ctx.estrutura.resistencia is not None:
        assert "ALVO passa por dentro" in nota.leitura or nota.nota <= 100


def test_fibonacci_sem_swing_fica_neutro_e_diz_por_que():
    ctx = contexto(serie_setup=serie([30.0] * 80))
    nota = nota_fibonacci(ctx)

    assert 40 <= nota.nota <= 60
    assert "sem grade" in nota.leitura or "fora das zonas" in nota.leitura


def test_gatilho_premia_rompimento_com_volume():
    forte = nota_gatilho(contexto(trigger=TriggerState.BREAKOUT_WITH_VOLUME))
    medio = nota_gatilho(contexto(trigger=TriggerState.MA_RECLAIM))
    nenhum = nota_gatilho(contexto(trigger=TriggerState.NONE))

    assert forte.nota > medio.nota > nenhum.nota
    assert nenhum.nota == 0.0


def test_gatilho_contra_a_operacao_zera():
    nota = nota_gatilho(
        contexto(direcao=Direction.LONG, trigger=TriggerState.BREAKOUT_WITH_VOLUME,
                 vies=Vies.BEARISH)
    )

    assert nota.nota == 0.0
    assert "contra a operacao" in nota.leitura


def test_risco_retorno_cresce_com_o_rr():
    ruim = nota_risco_retorno(contexto(entry=31.0, stop=30.5, target=31.4))  # RR 0,8
    bom = nota_risco_retorno(contexto(entry=31.0, stop=30.5, target=32.5))  # RR 3,0

    assert bom.nota > ruim.nota
    assert bom.nota == 100.0
    assert "risco/retorno de" in bom.leitura


def test_risco_retorno_com_stop_na_entrada_e_zero():
    assert nota_risco_retorno(contexto(entry=31.0, stop=31.0, target=32.0)).nota == 0.0


# ---------------------------------------------------------------------------
# pesos
# ---------------------------------------------------------------------------


def test_pesos_sao_configuraveis_e_mudam_o_score():
    ctx = contexto(trend=TrendState.SIDEWAYS, context=ContextState.NEUTRAL)

    padrao = calcular(ctx, PESOS_PADRAO).total
    so_tendencia = calcular(ctx, PesosScore(
        tendencia=10.0, estrutura=0, gatilho=0, risco_retorno=0, medias=0, volume=0,
        suporte_resistencia=0, momentum=0, vwap=0, fibonacci=0, volatilidade=0,
    )).total

    assert so_tendencia != padrao
    assert so_tendencia == calcular(ctx).componente("tendencia").nota


def test_peso_zero_desliga_o_componente():
    pesos = PESOS_PADRAO.atualizar(fibonacci=0.0)
    detalhado = calcular(contexto(), pesos)

    assert detalhado.componente("fibonacci") is None
    assert len(detalhado.componentes) == 10


def test_pesos_nao_precisam_somar_um():
    """Sao normalizados pela soma - da para dobrar um sem mexer nos outros."""
    dobrado = PESOS_PADRAO.atualizar(tendencia=PESOS_PADRAO.tendencia * 2)
    detalhado = calcular(contexto(), dobrado)

    assert 0 <= detalhado.total <= 100
    assert sum(dobrado.normalizados().values()) == pytest.approx(1.0)


def test_peso_negativo_e_recusado():
    with pytest.raises(PesosInvalidosError):
        PesosScore(tendencia=-1)


def test_todos_os_pesos_zerados_e_recusado():
    with pytest.raises(PesosInvalidosError):
        PesosScore(tendencia=0, estrutura=0, gatilho=0, risco_retorno=0, medias=0,
                   volume=0, suporte_resistencia=0, momentum=0, vwap=0, fibonacci=0,
                   volatilidade=0)


def test_componente_desconhecido_e_recusado():
    with pytest.raises(PesosInvalidosError, match="desconhecidos"):
        PESOS_PADRAO.atualizar(sorte=1.0)


def test_pesos_vao_e_voltam_de_dicionario():
    assert PesosScore.de_dict(PESOS_PADRAO.para_dict()) == PESOS_PADRAO


# ---------------------------------------------------------------------------
# transparencia
# ---------------------------------------------------------------------------


def test_contribuicao_de_cada_componente_soma_o_total():
    detalhado = calcular(contexto())
    soma = detalhado.soma_dos_pesos

    total = sum(c.contribuicao(soma) for c in detalhado.componentes)
    assert total == pytest.approx(detalhado.total, abs=0.05)


def test_ordenacao_por_contribuicao_e_por_pior_nota():
    detalhado = calcular(contexto())
    soma = detalhado.soma_dos_pesos

    contribuicoes = [c.contribuicao(soma) for c in detalhado.por_contribuicao()]
    assert contribuicoes == sorted(contribuicoes, reverse=True)

    piores = detalhado.piores(3)
    assert piores[0].nota <= piores[-1].nota


def test_score_serializa_inteiro():
    dados = calcular(contexto()).para_dict()
    texto = json.dumps(dados)

    assert set(dados) == {"total", "pesos", "componentes"}
    assert len(dados["componentes"]) == 11
    for c in dados["componentes"]:
        assert set(c) >= {"chave", "nome", "nota", "peso", "contribuicao", "leitura"}
    assert '"leitura"' in texto

