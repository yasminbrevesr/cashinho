"""A secao AUDITOR e a tela do resultado final."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.auditor import (
    ContrarianAuditor,
    Pipeline,
    pagina_resultado,
    resumo_auditoria,
    secao_auditor,
    trilha_do_fluxo,
)
from cashinho.core.confluencia.estados import ContextState
from cashinho.core.oportunidade import EstrategiaOportunidade, OpportunityEngine
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.core.strategy import de_vista, tela_analise
from cashinho.data.synthetic import SyntheticProvider

from .factories import AGORA, oportunidade

AUDITOR = ContrarianAuditor()
LIMPA = AUDITOR.auditar(oportunidade(score=80.0), agora=AGORA)
COM_PROBLEMAS = AUDITOR.auditar(
    oportunidade(score=90.0, context=ContextState.BEARISH,
                 expires_at=AGORA - timedelta(minutes=5)),
    agora=AGORA,
)


# --- as quatro secoes pedidas -------------------------------------------------


def test_secao_tem_as_quatro_partes():
    texto = secao_auditor(COM_PROBLEMAS)

    assert "AUDITOR" in texto
    assert "FATORES FAVORAVEIS" in texto
    assert "FATORES CONTRARIOS" in texto
    assert "RISCOS ENCONTRADOS" in texto
    assert "DECISAO" in texto


def test_favoraveis_listam_o_que_nao_foi_invalidado():
    texto = secao_auditor(LIMPA)

    assert "nao consegui invalidar" in texto
    for c in LIMPA.favoraveis:
        assert c.titulo in texto


def test_contrarios_mostram_o_desconto_no_score():
    texto = secao_auditor(COM_PROBLEMAS)

    assert "timeframes conflitantes" in texto
    assert "pts)" in texto


def test_riscos_encontrados_listam_as_criticas():
    texto = secao_auditor(COM_PROBLEMAS)

    assert "oportunidade expirada" in texto
    assert "janela terminou" in texto


def test_sem_criticas_a_secao_diz_isso():
    assert "nenhum risco critico" in secao_auditor(LIMPA)


def test_decisao_mostra_veredito_e_ajuste_de_score():
    aprovado = secao_auditor(LIMPA)
    reprovado = secao_auditor(COM_PROBLEMAS)

    assert "APROVADO PELO AUDITOR" in aprovado
    assert "REPROVADO PELO AUDITOR" in reprovado
    assert "score 90 ->" in reprovado
    assert "ajuste" in reprovado


def test_nao_verificados_aparecem_separados():
    texto = secao_auditor(LIMPA)

    if LIMPA.nao_verificadas:
        assert "NAO VERIFICADO" in texto


def test_cores_sao_opcionais():
    assert "\033[" not in secao_auditor(COM_PROBLEMAS, cores=False)
    assert "\033[" in secao_auditor(COM_PROBLEMAS, cores=True)


def test_resumo_cabe_em_uma_linha():
    linha = resumo_auditoria(COM_PROBLEMAS)

    assert "\n" not in linha
    assert "reprovado" in linha


# --- tela do fluxo -------------------------------------------------------------------


SERIE = SyntheticProvider(semente=11).candles("PETR4", "1m", 3)
ENGINE = OpportunityEngine()
PIPE = Pipeline(
    EstrategiaOportunidade(ENGINE), ENGINE, ContrarianAuditor(),
    RiskManager(RiskConfig(capital=100_000.0, max_trades_dia=200, perda_max_diaria_pct=100.0,
                           max_perdas_consecutivas=200),
                RiskState(capital_inicial=100_000.0)),
)
MTF = ENGINE.alimentar(SERIE)
RESULTADOS = [PIPE.executar(v, "PETR4") for v in MTF.replay()]
APROVADO = next((r for r in RESULTADOS if r.aprovado), None)
BARRADO = next(r for r in RESULTADOS if r.parou_em is not None)


def test_trilha_mostra_as_cinco_etapas_com_veredito():
    texto = trilha_do_fluxo(BARRADO)

    assert "FLUXO" in texto
    for nome in ("Strategy", "Opportunity", "Score", "Auditor", "Risk Manager"):
        assert nome in texto
    assert "nao executada" in texto


def test_pagina_mostra_o_veredito_final():
    if APROVADO is None:
        pytest.skip("nenhum resultado aprovado nesta serie")

    texto = pagina_resultado(APROVADO)
    assert "OPERACAO LIBERADA" in texto
    assert "AUDITOR" in texto
    assert "APROVADO PELO RISCO" in texto


def test_pagina_de_barrado_mostra_onde_parou():
    texto = pagina_resultado(BARRADO)

    assert "OPERACAO BARRADA" in texto
    assert BARRADO.parou_em.nome in texto


def test_secao_do_auditor_entra_na_tela_analise():
    estrategia = EstrategiaOportunidade(ENGINE)
    for vista in MTF.replay():
        if len(vista.fechados("5m")) == 0:
            continue
        sinal = estrategia.avaliar(
            de_vista(vista, "PETR4", papel_setup="setup", papel_tendencia="trend")
        )
        op = sinal.extras["oportunidade"]
        if op.score_detalhado is None:
            continue  # NAO OPERAR: nao ha score para abrir
        auditoria = ContrarianAuditor().auditar(op, vista, agora=vista.instante)
        sinal.extras["auditoria"] = auditoria

        texto = tela_analise(sinal)
        assert "AUDITOR" in texto
        assert "FATORES FAVORAVEIS" in texto
        assert "SCORE FINAL" in texto  # as outras secoes continuam
        return
    pytest.skip("nenhum sinal avaliavel")
