"""A agenda dentro do Opportunity Engine: desconta, bloqueia, e nunca aprova."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.confluencia.engine import config_padrao
from cashinho.core.mtf import MTFEngine
from cashinho.core.noticias import (
    AvaliadorDeEventos,
    ConfigEventos,
    FonteEmMemoria,
    SemFonte,
    Severidade,
    TipoDeEvento,
)
from cashinho.core.oportunidade import EstadoOportunidade, OpportunityEngine
from cashinho.data.synthetic import SyntheticProvider

from .factories import evento


@pytest.fixture(scope="module")
def cenario():
    serie = SyntheticProvider(semente=11).candles("PETR4", "1m", 5)
    vista = MTFEngine(config_padrao(), "PETR4").alimentar(serie).agora()
    return vista, serie.candles[-1].ts


def avaliar(cenario, eventos=(), config=None, fonte=None):
    vista, agora = cenario
    if fonte is None:
        fonte = FonteEmMemoria(eventos, agora)
    from cashinho.core.noticias import PoliticaDeEventos

    av = AvaliadorDeEventos(fonte, PoliticaDeEventos(config))
    return OpportunityEngine(eventos=av).avaliar(vista, "PETR4")


def test_sem_avaliador_nada_muda(cenario):
    vista, _ = cenario
    op = OpportunityEngine().avaliar(vista, "PETR4")

    assert op.eventos is None
    assert op.score_detalhado.penalidades == ()


def test_o_desconto_aparece_como_penalidade_e_o_bruto_e_preservado(cenario):
    vista, agora = cenario
    limpo = OpportunityEngine().avaliar(vista, "PETR4")

    op = avaliar(cenario, [evento(TipoDeEvento.RESULTADOS, minutos=200,
                                  severidade=Severidade.ALTA, instante=agora)])

    assert op.score_detalhado.total_bruto == limpo.score
    assert op.score < limpo.score
    assert op.score_detalhado.penalidades[0].chave == "eventos"
    assert op.score_detalhado.desconto > 0


def test_copom_na_janela_bloqueia_a_operacao(cenario):
    _, agora = cenario
    op = avaliar(cenario, [evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=20,
                                  severidade=Severidade.CRITICA, instante=agora)])

    assert op.estado is EstadoOportunidade.NAO_OPERAR
    assert op.estado.acionavel is False
    assert "JUROS" in op.motivo_do_estado


def test_o_bloqueio_nunca_promove_um_estado(cenario):
    """Bloqueio so rebaixa: nao existe evento que aprove uma oportunidade."""
    vista, agora = cenario
    limpo = OpportunityEngine().avaliar(vista, "PETR4")
    op = avaliar(cenario, [evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=20,
                                  severidade=Severidade.CRITICA, instante=agora)])

    assert not (limpo.estado.acionavel is False and op.estado.acionavel is True)


def test_notícia_nunca_aumenta_o_score(cenario):
    """Qualquer combinacao de evento so pode manter ou reduzir o score."""
    vista, agora = cenario
    limpo = OpportunityEngine().avaliar(vista, "PETR4")

    from cashinho.core.noticias import ViesDirecional

    for tipo in TipoDeEvento:
        for severidade in Severidade:
            for vies in ViesDirecional:
                op = avaliar(cenario, [evento(tipo, symbol="", minutos=100,
                                              severidade=severidade, vies=vies,
                                              instante=agora)])
                assert op.score <= limpo.score


def test_evento_de_outro_ativo_nao_afeta_este(cenario):
    vista, agora = cenario
    limpo = OpportunityEngine().avaliar(vista, "PETR4")

    op = avaliar(cenario, [evento(TipoDeEvento.RESULTADOS, symbol="VALE3", minutos=10,
                                  severidade=Severidade.CRITICA, instante=agora)])

    assert op.score == limpo.score
    assert op.estado is limpo.estado


def test_sem_fonte_a_oportunidade_sai_com_aviso_e_nao_bloqueada(cenario):
    op = avaliar(cenario, fonte=SemFonte())

    assert op.estado is not EstadoOportunidade.NAO_OPERAR or "evento" not in op.motivo_do_estado
    assert any("NOTICIAS INDISPONIVEIS" in a for a in op.warnings)


def test_da_para_exigir_agenda_para_operar(cenario):
    op = avaliar(cenario, fonte=SemFonte(), config=ConfigEventos(sem_fonte_bloqueia=True))

    assert op.estado is EstadoOportunidade.NAO_OPERAR
    assert "INDISPONIVEIS" in op.motivo_do_estado


def test_a_avaliacao_fica_anexada_a_oportunidade(cenario):
    _, agora = cenario
    op = avaliar(cenario, [evento(minutos=100, instante=agora)])

    assert op.eventos is not None
    assert op.eventos.eventos
    assert op.para_dict()["eventos"]["ajuste_de_score"] < 0


def test_a_oportunidade_com_eventos_serializa(cenario):
    import json

    _, agora = cenario
    op = avaliar(cenario, [evento(minutos=100, instante=agora)])

    json.dumps(op.para_dict())
