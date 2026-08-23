"""O fluxo obrigatorio: Strategy -> Opportunity -> Score -> Auditor -> Risk Manager."""

from __future__ import annotations

import json

import pytest

from cashinho.core.auditor import ContrarianAuditor, Pipeline, ResultadoFinal
from cashinho.core.auditor.checagens import ConfigAuditor
from cashinho.core.oportunidade import EstrategiaOportunidade, OpportunityEngine
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.data.synthetic import SyntheticProvider

SERIE = SyntheticProvider(semente=11).candles("PETR4", "1m", 3)


def _pipeline(auditor=None, risco=None):
    engine = OpportunityEngine()
    return engine, Pipeline(
        EstrategiaOportunidade(engine),
        engine,
        auditor or ContrarianAuditor(),
        risco or RiskManager(
            RiskConfig(capital=100_000.0, max_trades_dia=200, perda_max_diaria_pct=100.0,
                       max_perdas_consecutivas=200),
            RiskState(capital_inicial=100_000.0),
        ),
    )


def _rodar(pipe, engine, limite=None):
    mtf = engine.alimentar(SERIE)
    saida = []
    for vista in mtf.replay():
        saida.append(pipe.executar(vista, "PETR4"))
        if limite and len(saida) >= limite:
            break
    return saida


ENGINE, PIPE = _pipeline()
RESULTADOS = _rodar(PIPE, ENGINE)
APROVADOS = [r for r in RESULTADOS if r.aprovado]


# --- a ordem do fluxo ---------------------------------------------------------


def test_as_cinco_etapas_estao_na_ordem_obrigatoria():
    assert Pipeline.ETAPAS == ("Strategy", "Opportunity", "Score", "Auditor", "Risk Manager")

    for r in RESULTADOS[::200]:
        assert [e.nome for e in r.etapas] == list(Pipeline.ETAPAS)
        assert [e.ordem for e in r.etapas] == [1, 2, 3, 4, 5]


def test_toda_execucao_registra_as_cinco_etapas():
    for r in RESULTADOS[::150]:
        assert len(r.etapas) == 5


def test_etapas_seguintes_a_uma_barrada_nao_executam():
    barrados = [r for r in RESULTADOS if r.parou_em is not None]

    assert barrados
    for r in barrados[:20]:
        parada = r.parou_em
        seguintes = [e for e in r.etapas if e.ordem > parada.ordem]
        assert all(not e.executada for e in seguintes)


def test_o_risco_nunca_e_consultado_sem_passar_pelo_auditor():
    """Nao existe caminho que chegue ao Risk Manager pulando o auditor."""
    for r in RESULTADOS:
        risco = next(e for e in r.etapas if e.nome == "Risk Manager")
        auditor = next(e for e in r.etapas if e.nome == "Auditor")
        if risco.executada:
            assert auditor.executada and auditor.passou


def test_aprovado_exige_as_cinco_etapas():
    for r in APROVADOS:
        assert all(e.executada and e.passou for e in r.etapas)
        assert r.decisao_de_risco is not None
        assert r.decisao_de_risco.allowed


def test_resumo_diz_onde_parou():
    barrado = next(r for r in RESULTADOS if r.parou_em is not None)

    assert "barrado em" in barrado.resumo
    assert barrado.parou_em.nome in barrado.resumo


# --- o veto do auditor no fluxo -------------------------------------------------------


def test_auditor_intransigente_barra_tudo_antes_do_risco():
    duro = ContrarianAuditor(score_minimo_pos_auditoria=101.0)
    engine, pipe = _pipeline(auditor=duro)
    resultados = _rodar(pipe, engine)

    assert not any(r.aprovado for r in resultados)
    barrados = [r for r in resultados if r.parou_em and r.parou_em.nome == "Auditor"]
    assert barrados
    for r in barrados:
        assert r.decisao_de_risco is None  # o risco nem foi consultado


def test_uma_critica_do_auditor_barra_mesmo_com_score_alto():
    """Volume critico: o auditor derruba oportunidades que o engine aprovou."""
    exigente = ContrarianAuditor(ConfigAuditor(volume_critico=99.0))
    engine, pipe = _pipeline(auditor=exigente)
    resultados = _rodar(pipe, engine)

    barrados = [r for r in resultados if r.parou_em and r.parou_em.nome == "Auditor"]
    assert barrados
    for r in barrados[:5]:
        assert r.auditoria.critical_rejections
        assert r.opportunity.score >= 0  # o engine tinha aprovado
        assert not r.aprovado


def test_auditor_roda_mesmo_quando_a_oportunidade_e_aprovada():
    assert APROVADOS
    for r in APROVADOS[:5]:
        assert r.auditoria is not None
        assert r.auditoria.approved


# --- o risco no fim do fluxo -------------------------------------------------------------


def test_risco_bloqueado_barra_na_ultima_etapa():
    risco = RiskManager(RiskConfig(capital=100_000.0), RiskState(capital_inicial=100_000.0))
    risco.acionar_kill_switch("teste de fluxo")
    engine, pipe = _pipeline(risco=risco)
    resultados = _rodar(pipe, engine)

    barrados = [r for r in resultados if r.parou_em and r.parou_em.nome == "Risk Manager"]
    assert barrados
    for r in barrados[:3]:
        assert r.auditoria.approved  # passou pelo auditor
        assert r.decisao_de_risco.allowed is False
        assert "kill switch" in r.decisao_de_risco.reason


def test_o_fluxo_completo_produz_quantidade_apenas_no_fim():
    """Quem dimensiona e' o Risk Manager, na ultima etapa."""
    r = APROVADOS[0]

    assert r.opportunity.para_dict().get("quantidade") is None
    assert r.decisao_de_risco.position_size > 0


# --- serializacao ---------------------------------------------------------------------------


def test_resultado_serializa_inteiro():
    dados = APROVADOS[0].para_dict()
    texto = json.dumps(dados)

    assert dados["aprovado"] is True
    assert len(dados["etapas"]) == 5
    assert dados["auditoria"]["approved"] is True
    assert '"risco"' in texto


def test_resultado_sem_etapas_nao_e_aprovado():
    vazio = ResultadoFinal(symbol="PETR4", instante=SERIE.last.ts)

    assert vazio.aprovado is False
    assert vazio.parou_em is None
