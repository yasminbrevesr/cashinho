"""A tela: estado, score aberto e integracao com a tela Analise."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.oportunidade import (
    EstadoOportunidade,
    EstrategiaOportunidade,
    OpportunityEngine,
    faixa_de_estado,
    linha_de_lista,
    pagina_oportunidade,
    painel_score,
    resumo_score,
)
from cashinho.core.strategy import Action, de_vista, tela_analise
from cashinho.data.synthetic import SyntheticProvider

SERIE = SyntheticProvider(semente=11).candles("PETR4", "1m", 3)
ENGINE = OpportunityEngine()
MTF = ENGINE.alimentar(SERIE)
TODAS = [ENGINE.avaliar(v, "PETR4") for v in MTF.replay()]
APROVADA = next((o for o in TODAS if o.acionavel), None)
ESPERANDO = next(o for o in TODAS if o.estado is EstadoOportunidade.AGUARDANDO_GATILHO)
SEM_OPERACAO = TODAS[0]


# --- estado ------------------------------------------------------------------


def test_faixa_mostra_o_estado_em_destaque():
    texto = faixa_de_estado(ESPERANDO)

    assert "AGUARDANDO GATILHO" in texto
    assert "╔" in texto


@pytest.mark.parametrize("rotulo", ["SETUP APROVADO", "AGUARDANDO GATILHO",
                                    "SETUP REJEITADO", "NAO OPERAR", "EXPIRADO"])
def test_todos_os_estados_tem_rotulo_proprio(rotulo):
    assert rotulo in {e.value for e in EstadoOportunidade}


def test_pagina_mostra_expirado_depois_do_prazo():
    if APROVADA is None:
        pytest.skip("nenhuma oportunidade aprovada nesta serie")
    depois = APROVADA.expires_at + timedelta(minutes=5)
    texto = pagina_oportunidade(APROVADA, agora=depois)

    assert "EXPIRADO" in texto
    assert "a janela terminou" in texto


# --- score aberto ---------------------------------------------------------------


def test_painel_mostra_as_onze_notas_e_o_score_final():
    op = APROVADA or ESPERANDO
    texto = painel_score(op.score_detalhado)

    for nome in ("Tendencia", "Volume", "Estrutura", "Momentum", "Risco/Retorno",
                 "VWAP", "Medias", "Volatilidade", "Suporte/Resistencia",
                 "Fibonacci", "Qualidade do gatilho"):
        assert nome in texto
    assert "SCORE FINAL" in texto


def test_painel_mostra_peso_e_contribuicao_de_cada_componente():
    texto = painel_score((APROVADA or ESPERANDO).score_detalhado)

    assert "peso" in texto
    assert "contribui" in texto


def test_painel_explica_cada_nota():
    """Nenhum numero sem a conta que o gerou."""
    op = APROVADA or ESPERANDO
    texto = painel_score(op.score_detalhado)

    for c in op.score_detalhado.componentes:
        assert c.leitura in texto


def test_painel_pode_esconder_os_pesos():
    texto = painel_score((APROVADA or ESPERANDO).score_detalhado, mostrar_peso=False)

    assert "SCORE FINAL" in texto
    assert "contribui" not in texto


def test_resumo_do_score_cabe_em_uma_linha():
    linha = resumo_score((APROVADA or ESPERANDO).score_detalhado)

    assert "\n" not in linha
    assert "FINAL" in linha


# --- pagina completa ----------------------------------------------------------------


def test_pagina_traz_operacao_timeframes_score_motivos_e_invalidacao():
    op = APROVADA or ESPERANDO
    texto = pagina_oportunidade(op)

    assert "OPERACAO" in texto
    assert "TIMEFRAMES" in texto
    assert "SCORE" in texto
    assert "MOTIVOS" in texto
    assert "INVALIDACAO" in texto


def test_pagina_mostra_os_quatro_timeframes():
    texto = pagina_oportunidade(APROVADA or ESPERANDO)

    assert "contexto 60m" in texto
    assert "tendencia 15m" in texto
    assert "setup 5m" in texto
    assert "gatilho 1m" in texto


def test_pagina_de_nao_operar_explica_o_motivo():
    texto = pagina_oportunidade(SEM_OPERACAO)

    assert "NAO OPERAR" in texto
    assert "sem candle fechado" in texto


def test_pagina_mostra_avisos_quando_existem():
    com_aviso = next((o for o in TODAS if o.warnings), None)
    if com_aviso is None:
        pytest.skip("nenhuma oportunidade com aviso nesta serie")

    assert "AVISOS" in pagina_oportunidade(com_aviso)


def test_cores_sao_opcionais():
    op = APROVADA or ESPERANDO
    assert "\033[" not in pagina_oportunidade(op, cores=False)
    assert "\033[" in pagina_oportunidade(op, cores=True)


def test_linha_de_lista_cabe_em_uma_linha():
    linha = linha_de_lista(APROVADA or ESPERANDO)

    assert "\n" not in linha
    assert "PETR4" in linha and "score" in linha


# --- integracao com a tela Analise ----------------------------------------------------


def test_score_entra_na_tela_analise():
    estrategia = EstrategiaOportunidade(ENGINE)
    alvo = None
    for vista in MTF.replay():
        if len(vista.fechados("5m")) == 0:
            continue
        sinal = estrategia.avaliar(
            de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
        )
        if sinal.action.acionavel:
            alvo = sinal
            break
    if alvo is None:
        pytest.skip("nenhum sinal acionavel nesta serie")

    texto = tela_analise(alvo)
    assert "SCORE FINAL" in texto
    assert "ANALISE MULTI-TIMEFRAME" in texto
    assert "JUSTIFICATIVAS" in texto


def test_estrategia_traduz_estado_em_acao():
    estrategia = EstrategiaOportunidade(ENGINE)
    for vista in list(MTF.replay())[::40]:
        if len(vista.fechados("5m")) == 0:
            continue
        sinal = estrategia.avaliar(
            de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
        )
        op = sinal.extras["oportunidade"]
        if op.estado is EstadoOportunidade.APROVADO:
            assert sinal.action.acionavel
        elif op.estado is EstadoOportunidade.NAO_OPERAR:
            assert sinal.action is Action.NONE
        else:
            assert sinal.action is Action.WAIT


def test_confianca_do_sinal_espelha_o_score():
    estrategia = EstrategiaOportunidade(ENGINE)
    vista = list(MTF.replay())[-1]
    sinal = estrategia.avaliar(
        de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
    )

    assert sinal.confidence == pytest.approx(sinal.extras["oportunidade"].score / 100.0, abs=0.01)


def test_estrategia_esta_registrada():
    from cashinho.core.strategy import disponiveis, obter

    assert "oportunidade-score" in disponiveis()
    assert isinstance(obter("oportunidade-score"), EstrategiaOportunidade)
