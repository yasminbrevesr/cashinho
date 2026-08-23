"""O evento estruturado e a agenda."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.noticias import (
    AgendaDeEventos,
    Disponibilidade,
    Evento,
    EventoInvalidoError,
    Severidade,
    TipoDeEvento,
    ViesDirecional,
    agenda_indisponivel,
)
from cashinho.models import Direction

from .factories import AGORA, agenda, evento


# --- os campos pedidos ---------------------------------------------------------


def test_o_evento_tem_os_campos_do_contrato():
    dados = evento().para_dict()

    assert set(dados) >= {"event_type", "symbol", "timestamp", "severity",
                          "directional_bias", "confidence", "source"}


def test_os_tipos_pedidos_existem():
    valores = {t.value for t in TipoDeEvento}

    assert {"resultados", "fato_relevante", "decisao_de_juros", "inflacao",
            "payroll", "evento_corporativo"} == valores


def test_evento_sem_origem_e_recusado():
    """Sem source nao da para julgar se o registro merece confianca."""
    with pytest.raises(EventoInvalidoError, match="de onde veio"):
        evento(fonte="  ")


def test_confianca_fora_da_faixa_e_recusada():
    with pytest.raises(EventoInvalidoError, match="entre 0 e 1"):
        evento(confianca=1.4)


def test_o_simbolo_e_normalizado():
    assert evento(symbol="petr4").symbol == "PETR4"


# --- abrangencia ------------------------------------------------------------------


def test_evento_macro_atinge_qualquer_ativo():
    juros = evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="")

    assert juros.mercado_inteiro is True
    assert juros.atinge("PETR4") and juros.atinge("VALE3")
    assert juros.alvo == "MERCADO"


def test_evento_de_ativo_nao_atinge_outro():
    resultados = evento(symbol="PETR4")

    assert resultados.atinge("PETR4") is True
    assert resultados.atinge("VALE3") is False


def test_minutos_ate_diz_o_sentido_do_tempo():
    assert evento(minutos=30).minutos_ate(AGORA) == pytest.approx(30)
    assert evento(minutos=-45).minutos_ate(AGORA) == pytest.approx(-45)


# --- vies: agravante, nunca instrucao ------------------------------------------------


def test_vies_de_alta_contraria_uma_venda():
    e = evento(vies=ViesDirecional.ALTA)

    assert e.contraria(Direction.SHORT) is True
    assert e.contraria(Direction.LONG) is False


def test_vies_indefinido_nao_contraria_ninguem():
    e = evento(vies=ViesDirecional.INDEFINIDO)

    assert e.contraria(Direction.LONG) is False
    assert e.contraria(Direction.SHORT) is False


def test_nao_existe_o_espelho_de_contraria():
    """Nenhum metodo diz que a notícia CONFIRMA uma operacao."""
    metodos = dir(evento())

    assert not [m for m in metodos if "confirma" in m and m != "confirmado"]


# --- a agenda -------------------------------------------------------------------------


def test_agenda_vazia_disponivel_e_diferente_de_agenda_indisponivel():
    """'Nao ha evento' e 'nao sabemos' nao podem ser a mesma coisa."""
    vazia = agenda([])
    sem = agenda_indisponivel("a fonte caiu")

    assert len(vazia) == len(sem) == 0
    assert vazia.confiavel is True
    assert sem.confiavel is False
    assert sem.rotulo == "NOTICIAS INDISPONIVEIS"


def test_a_agenda_filtra_por_ativo():
    a = agenda([evento(symbol="PETR4"), evento(symbol="VALE3"),
                evento(TipoDeEvento.PAYROLL, symbol="")])

    assert len(a.para("PETR4")) == 2  # o do ativo + o macro


def test_a_janela_olha_para_a_frente_e_para_tras():
    a = agenda([evento(minutos=20), evento(minutos=-20), evento(minutos=300)])

    assert len(a.na_janela(AGORA, antes_min=60, depois_min=60)) == 2


def test_a_janela_respeita_os_lados_separadamente():
    a = agenda([evento(minutos=45), evento(minutos=-45)])

    so_futuro = a.na_janela(AGORA, antes_min=60, depois_min=10)
    assert len(so_futuro) == 1
    assert so_futuro[0].minutos_ate(AGORA) > 0


def test_a_janela_sai_ordenada_pela_proximidade():
    a = agenda([evento(minutos=50), evento(minutos=5), evento(minutos=-20)])

    ordem = [abs(e.minutos_ate(AGORA)) for e in a.na_janela(AGORA, 60, 60)]
    assert ordem == sorted(ordem)


def test_proximos_traz_so_o_que_ainda_vai_acontecer():
    a = agenda([evento(minutos=-30), evento(minutos=30), evento(minutos=90)])

    assert len(a.proximos(AGORA)) == 2


def test_a_idade_da_agenda_e_calculavel():
    a = agenda([], instante=AGORA)

    assert a.idade_em(AGORA + timedelta(hours=3)) == pytest.approx(180)


def test_a_agenda_serializa_para_json():
    import json

    json.dumps(agenda([evento()]).para_dict())
