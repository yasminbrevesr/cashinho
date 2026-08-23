"""As fontes: o que vira evento, o que e' descartado, e quando a agenda vence."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.noticias import (
    Disponibilidade,
    EventoInvalidoError,
    FonteArquivo,
    FonteComposta,
    FonteEmMemoria,
    SemFonte,
    Severidade,
    TipoDeEvento,
    ViesDirecional,
    evento_de_dict,
)

from .factories import AGORA, arquivo_de_eventos, bruto, evento


# --- conversao de registro em evento ---------------------------------------------


def test_converte_um_registro_completo():
    e = evento_de_dict(bruto())

    assert e.event_type is TipoDeEvento.RESULTADOS
    assert e.severity is Severidade.ALTA
    assert e.source == "calendario manual"


def test_tipo_desconhecido_e_recusado_e_nao_encaixado_no_parecido():
    with pytest.raises(EventoInvalidoError, match="tipo de evento desconhecido"):
        evento_de_dict(bruto(tipo="guidance"))


def test_severidade_desconhecida_e_recusada():
    with pytest.raises(EventoInvalidoError, match="severidade"):
        evento_de_dict(bruto(severidade="gravissima"))


def test_vies_desconhecido_e_recusado():
    with pytest.raises(EventoInvalidoError, match="vies"):
        evento_de_dict(bruto(directional_bias="para cima"))


def test_campo_obrigatorio_faltando_e_recusado():
    registro = bruto()
    del registro["timestamp"]

    with pytest.raises(EventoInvalidoError, match="obrigatorios"):
        evento_de_dict(registro)


def test_data_invalida_e_recusada():
    with pytest.raises(EventoInvalidoError, match="timestamp invalido"):
        evento_de_dict(bruto(timestamp="ontem a tarde"))


def test_confianca_nao_numerica_e_recusada():
    with pytest.raises(EventoInvalidoError, match="confidence"):
        evento_de_dict(bruto(confidence="alta"))


def test_data_sem_fuso_assume_o_horario_de_brasilia():
    e = evento_de_dict(bruto(timestamp="2026-08-21T14:00:00"))

    assert e.timestamp.utcoffset() is not None


def test_a_fonte_do_arquivo_vale_como_padrao_do_registro():
    registro = bruto()
    del registro["source"]

    assert evento_de_dict(registro, "agenda da corretora").source == "agenda da corretora"


def test_registro_sem_fonte_nenhuma_e_recusado():
    registro = bruto()
    del registro["source"]

    with pytest.raises(EventoInvalidoError):
        evento_de_dict(registro)


# --- arquivo -----------------------------------------------------------------------


def test_le_o_calendario(tmp_path):
    caminho = arquivo_de_eventos(tmp_path, [bruto(), bruto(symbol="VALE3")])

    a = FonteArquivo(caminho).carregar(AGORA)

    assert a.confiavel is True
    assert len(a) == 2
    assert a.disponibilidade is Disponibilidade.DISPONIVEL


def test_os_eventos_saem_em_ordem_cronologica(tmp_path):
    caminho = arquivo_de_eventos(tmp_path, [bruto(minutos=90), bruto(minutos=10)])

    eventos = FonteArquivo(caminho).carregar(AGORA).eventos
    assert [e.timestamp for e in eventos] == sorted(e.timestamp for e in eventos)


def test_arquivo_que_nao_existe_vira_sem_fonte(tmp_path):
    a = FonteArquivo(tmp_path / "nao-existe.json").carregar(AGORA)

    assert a.disponibilidade is Disponibilidade.SEM_FONTE
    assert a.confiavel is False
    assert "nao encontrado" in a.motivo


def test_json_quebrado_vira_indisponivel_e_nao_excecao(tmp_path):
    caminho = tmp_path / "eventos.json"
    caminho.write_text("{isso nao e json", encoding="utf-8")

    a = FonteArquivo(caminho).carregar(AGORA)

    assert a.disponibilidade is Disponibilidade.INDISPONIVEL
    assert len(a) == 0


def test_arquivo_sem_data_de_atualizacao_nao_vale(tmp_path):
    """Sem 'atualizado_em' nao da para saber se a agenda esta fresca."""
    caminho = arquivo_de_eventos(tmp_path, [bruto()], atualizado_em=None)

    a = FonteArquivo(caminho).carregar(AGORA)

    assert a.confiavel is False
    assert "atualizacao" in a.motivo


def test_agenda_velha_vira_desatualizada_mas_ainda_e_exibida(tmp_path):
    caminho = arquivo_de_eventos(tmp_path, [bruto()],
                                 atualizado_em=AGORA - timedelta(days=3))

    a = FonteArquivo(caminho).carregar(AGORA)

    assert a.disponibilidade is Disponibilidade.DESATUALIZADA
    assert a.confiavel is False
    assert len(a) == 1               # a tela mostra, a decisao ignora
    assert a.rotulo == "NOTICIAS INDISPONIVEIS"


def test_a_validade_e_configuravel(tmp_path):
    caminho = arquivo_de_eventos(tmp_path, [bruto()],
                                 atualizado_em=AGORA - timedelta(hours=20))

    assert FonteArquivo(caminho, validade_min=12 * 60).carregar(AGORA).confiavel is False
    assert FonteArquivo(caminho, validade_min=48 * 60).carregar(AGORA).confiavel is True


def test_registro_invalido_e_descartado_com_motivo_sem_derrubar_o_resto(tmp_path):
    caminho = arquivo_de_eventos(tmp_path, [bruto(), bruto(tipo="fofoca")])

    a = FonteArquivo(caminho).carregar(AGORA)

    assert len(a) == 1
    assert len(a.descartados) == 1
    assert "fofoca" in a.descartados[0]


def test_formato_inesperado_e_recusado(tmp_path):
    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps([{"event_type": "resultados"}]), encoding="utf-8")

    assert FonteArquivo(caminho).carregar(AGORA).confiavel is False


# --- composicao e ausencia -------------------------------------------------------------


def test_a_composta_soma_os_eventos():
    a = FonteComposta([FonteEmMemoria([evento(symbol="PETR4")], AGORA),
                       FonteEmMemoria([evento(symbol="VALE3")], AGORA)]).carregar(AGORA)

    assert len(a) == 2
    assert a.confiavel is True


def test_a_composta_assume_o_estado_do_elo_mais_fraco(tmp_path):
    """Uma fonte que falhou deixa um buraco que ninguem ve de dentro."""
    boa = FonteEmMemoria([evento()], AGORA)
    ruim = FonteArquivo(tmp_path / "nao-existe.json")

    a = FonteComposta([boa, ruim]).carregar(AGORA)

    assert a.confiavel is False
    assert len(a) == 1


def test_composta_vazia_e_recusada():
    with pytest.raises(ValueError):
        FonteComposta([])


def test_sem_fonte_diz_que_esta_operando_as_cegas():
    a = SemFonte().carregar(AGORA)

    assert a.disponibilidade is Disponibilidade.SEM_FONTE
    assert "as cegas" in a.motivo
