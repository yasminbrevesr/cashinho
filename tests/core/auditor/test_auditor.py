"""O veredito do auditor: contrato de saida e poder de veto."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.auditor import AuditResult, ContrarianAuditor, Severidade
from cashinho.core.auditor.checagens import ConfigAuditor
from cashinho.core.confluencia.estados import ContextState, TrendState
from cashinho.core.oportunidade.estados import EstadoOportunidade
from cashinho.models import Direction

from .factories import AGORA, estrutura, nivel, oportunidade


AUDITOR = ContrarianAuditor()


def _auditar(op=None, **kwargs):
    return AUDITOR.auditar(op or oportunidade(), agora=kwargs.pop("agora", AGORA), **kwargs)


# --- contrato de saida ------------------------------------------------------------


def test_a_saida_tem_os_cinco_campos_pedidos():
    r = _auditar()

    assert isinstance(r.approved, bool)
    assert isinstance(r.warnings, tuple)
    assert isinstance(r.critical_rejections, tuple)
    assert isinstance(r.score_adjustment, float)
    assert isinstance(r.reasons, tuple)


def test_as_onze_frentes_sao_rodadas_sempre():
    r = _auditar()

    assert len(r.checagens) == 11


def test_saida_serializa():
    dados = _auditar().para_dict()
    texto = json.dumps(dados)

    assert set(dados) >= {"approved", "warnings", "critical_rejections",
                          "score_adjustment", "reasons"}
    assert '"checagens"' in texto


# --- poder de veto -------------------------------------------------------------------


def test_rejeicao_critica_impede_a_aprovacao():
    """Score alto nao salva: uma critica derruba."""
    expirada = oportunidade(score=98.0, expires_at=AGORA - timedelta(minutes=10))
    r = _auditar(expirada)

    assert r.approved is False
    assert r.critical_rejections
    assert "oportunidade expirada" in r.critical_rejections[0]


def test_criticas_aparecem_separadas_dos_alertas():
    op = oportunidade(
        score=90.0,
        expires_at=AGORA - timedelta(minutes=1),  # critica
        context=ContextState.BEARISH,  # alerta (uma camada contra)
    )
    r = _auditar(op)

    assert len(r.critical_rejections) >= 1
    assert any("timeframes" in w for w in r.warnings)
    assert r.approved is False


def test_varias_criticas_sao_todas_listadas():
    op = oportunidade(
        score=95.0,
        entry=31.0, stop=29.5, target=31.2,  # stop distante + RR ruim
        expires_at=AGORA - timedelta(minutes=1),  # expirada
    )
    r = _auditar(op)

    assert len(r.critical_rejections) >= 3
    assert r.approved is False


def test_sem_criticas_e_com_score_bom_o_auditor_aprova():
    r = _auditar(oportunidade(score=80.0))

    assert r.approved is True
    assert r.critical_rejections == ()
    assert "nao encontraram problema" in r.motivo


# --- ajuste de score ---------------------------------------------------------------------


def test_alertas_descontam_do_score():
    limpa = _auditar(oportunidade(score=80.0))
    com_alerta = _auditar(oportunidade(score=80.0, context=ContextState.BEARISH))

    assert limpa.score_adjustment == 0.0
    assert com_alerta.score_adjustment < 0
    assert com_alerta.score_final < com_alerta.score_original


def test_score_final_nunca_sai_da_faixa():
    op = oportunidade(score=5.0, entry=31.0, stop=29.0, target=31.1,
                      expires_at=AGORA - timedelta(minutes=30))
    r = _auditar(op)

    assert 0.0 <= r.score_final <= 100.0


def test_score_derrubado_pelos_descontos_reprova():
    magro = ContrarianAuditor(score_minimo_pos_auditoria=75.0)
    op = oportunidade(score=78.0, context=ContextState.BEARISH)  # alerta desconta 6
    r = magro.auditar(op, agora=AGORA)

    assert r.approved is False
    assert "abaixo do minimo" in r.motivo


def test_desconto_por_severidade_e_configuravel():
    duro = ContrarianAuditor(ConfigAuditor(desconto_alerta=30.0))
    r = duro.auditar(oportunidade(score=80.0, context=ContextState.BEARISH), agora=AGORA)

    assert r.score_adjustment == -30.0


# --- respeito ao fluxo -----------------------------------------------------------------------


def test_o_auditor_nao_aprova_o_que_o_engine_nao_aprovou():
    esperando = oportunidade(score=90.0, estado=EstadoOportunidade.AGUARDANDO_GATILHO)
    r = _auditar(esperando)

    assert r.approved is False
    assert "nao aprova o que o engine nao aprovou" in r.motivo


@pytest.mark.parametrize("estado", [
    EstadoOportunidade.REJEITADO,
    EstadoOportunidade.NAO_OPERAR,
    EstadoOportunidade.EXPIRADO,
])
def test_nenhum_estado_nao_aprovado_passa(estado):
    assert _auditar(oportunidade(score=99.0, estado=estado)).approved is False


# --- favoraveis, contrarios e nao verificados -------------------------------------------------------


def test_favoraveis_sao_as_frentes_que_nao_conseguiram_invalidar():
    r = _auditar(oportunidade(score=80.0))

    assert len(r.favoraveis) >= 5
    for c in r.favoraveis:
        assert c.passou and c.verificada
        assert c.detalhe


def test_checagem_sem_dado_nao_vira_favoravel():
    """Sem vista, as checagens de mercado ficam sem verificacao."""
    r = _auditar()
    nao_verificadas = {c.chave for c in r.nao_verificadas}

    assert "baixo_volume" in nao_verificadas
    assert all(c.chave not in nao_verificadas for c in r.favoraveis)


def test_razoes_priorizam_criticas_e_alertas():
    op = oportunidade(score=90.0, expires_at=AGORA - timedelta(minutes=1))
    r = _auditar(op)

    assert r.reasons
    assert "janela terminou" in r.reasons[0]


def test_sem_problemas_as_razoes_mostram_o_que_foi_checado():
    r = _auditar(oportunidade(score=80.0))

    assert r.reasons
    assert len(r.reasons) <= 3


# --- com dados de mercado ---------------------------------------------------------------------------------


def test_com_vista_as_checagens_de_mercado_rodam():
    from cashinho.core.oportunidade import OpportunityEngine
    from cashinho.data.synthetic import SyntheticProvider

    serie = SyntheticProvider(semente=11).candles("PETR4", "1m", 3)
    engine = OpportunityEngine()
    mtf = engine.alimentar(serie)
    vista = mtf.agora()
    op = engine.avaliar(vista, "PETR4")

    r = ContrarianAuditor().auditar(op, vista, agora=vista.instante)

    assert len(r.nao_verificadas) < 6  # a maioria pode ser checada agora
    assert len(r.checagens) == 11


def test_oportunidade_sem_niveis_nao_gera_critica_inventada():
    """Auditar um NAO OPERAR nao pode produzir rejeicoes de uma operacao inexistente."""
    from cashinho.core.oportunidade.estados import EstadoOportunidade

    vazia = oportunidade(estado=EstadoOportunidade.NAO_OPERAR, entry=0.0, stop=0.0,
                         target=0.0, score=0.0)
    r = _auditar(vazia)

    assert r.approved is False
    assert "nao aprova o que o engine nao aprovou" in r.motivo
    assert not any("risco/retorno" in c for c in r.critical_rejections)
    assert any(c.chave == "risco_retorno_ruim" for c in r.nao_verificadas)
