"""A divisao dos dados e o cofre que protege o TEST."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from cashinho.core.validacao import (
    CofreDeTeste,
    DivisaoDeDados,
    DivisaoInvalidaError,
    Particao,
    TesteProtegidoError,
    dias_da_serie,
    garantir_sem_teste,
)

from .factories import serie_de_dias


# --- divisao por percentual -------------------------------------------------------


def test_as_tres_particoes_pedidas_existem():
    assert {p.rotulo for p in Particao} == {"TRAIN", "VALIDATION", "TEST"}


def test_divide_por_percentual():
    serie = serie_de_dias(dias=10)
    d = DivisaoDeDados.por_percentual(serie, 0.6, 0.2, 0.2)

    assert d.treino.dias == 6
    assert d.validacao.dias == 2
    assert d.teste.dias == 2


def test_a_divisao_e_cronologica():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))

    assert d.treino.fim < d.validacao.inicio
    assert d.validacao.fim < d.teste.inicio


def test_as_particoes_nao_se_sobrepoem():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    dias_treino = {c.ts.date() for c in d.treino.serie.candles}
    dias_validacao = {c.ts.date() for c in d.validacao.serie.candles}
    dias_teste = {c.ts.date() for c in d.teste.serie.candles}

    assert not (dias_treino & dias_validacao)
    assert not (dias_validacao & dias_teste)
    assert not (dias_treino & dias_teste)


def test_o_corte_acontece_entre_pregoes_e_nao_no_meio_de_um():
    """Cortar as 14h deixaria a validacao com meio pregao que ela nao viveu."""
    serie = serie_de_dias(dias=10)
    d = DivisaoDeDados.por_percentual(serie)

    for janela in d.janelas:
        dias = {c.ts.date() for c in janela.serie.candles}
        for dia in dias:
            no_dia_original = sum(1 for c in serie.candles if c.ts.date() == dia)
            no_dia_da_janela = sum(1 for c in janela.serie.candles if c.ts.date() == dia)
            assert no_dia_da_janela == no_dia_original


def test_percentuais_que_nao_somam_um_sao_recusados():
    with pytest.raises(DivisaoInvalidaError, match="somar"):
        DivisaoDeDados.por_percentual(serie_de_dias(dias=10), 0.5, 0.3, 0.3)


def test_fatia_zerada_e_recusada():
    with pytest.raises(DivisaoInvalidaError):
        DivisaoDeDados.por_percentual(serie_de_dias(dias=10), 0.8, 0.2, 0.0)


def test_serie_curta_demais_e_recusada():
    with pytest.raises(DivisaoInvalidaError, match="ao menos 3"):
        DivisaoDeDados.por_percentual(serie_de_dias(dias=2))


# --- divisao por data ----------------------------------------------------------------


def test_divide_por_data():
    serie = serie_de_dias(dias=10)
    dias = dias_da_serie(serie)
    d = DivisaoDeDados.por_data(serie, dias[5], dias[7])

    assert d.treino.fim == dias[5]
    assert d.validacao.inicio == dias[6]
    assert d.validacao.fim == dias[7]
    assert d.teste.inicio == dias[8]


def test_datas_fora_de_ordem_sao_recusadas():
    dias = dias_da_serie(serie_de_dias(dias=10))
    with pytest.raises(DivisaoInvalidaError, match="antes"):
        DivisaoDeDados.por_data(serie_de_dias(dias=10), dias[7], dias[3])


def test_data_que_esvazia_uma_particao_e_recusada():
    serie = serie_de_dias(dias=10)
    dias = dias_da_serie(serie)
    with pytest.raises(DivisaoInvalidaError, match="vazia"):
        DivisaoDeDados.por_data(serie, dias[-2], dias[-1])  # teste fica vazio


# --- aquecimento -----------------------------------------------------------------------


def test_o_aquecimento_traz_dias_anteriores_sem_mexer_na_janela():
    serie = serie_de_dias(dias=10)
    d = DivisaoDeDados.por_percentual(serie)

    com = d.validacao.com_aquecimento(serie, dias=3)
    assert len(com) > d.validacao.candles
    assert min(c.ts.date() for c in com.candles) < d.validacao.inicio
    assert max(c.ts.date() for c in com.candles) == d.validacao.fim


def test_sem_aquecimento_a_serie_e_a_propria_janela():
    serie = serie_de_dias(dias=10)
    d = DivisaoDeDados.por_percentual(serie)

    assert d.validacao.com_aquecimento(serie, dias=0) is d.validacao.serie


# --- o cofre ------------------------------------------------------------------------------


def test_o_cofre_so_aceita_a_particao_test():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))

    with pytest.raises(TesteProtegidoError, match="apenas a particao TEST"):
        CofreDeTeste(d.treino)


def test_metadados_nao_contam_como_abertura():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))
    cofre = CofreDeTeste(d.teste)

    meta = cofre.espiar_metadados()
    assert meta["dias"] == d.teste.dias
    assert cofre.foi_aberto is False
    assert cofre.vezes == 0


def test_abrir_exige_motivo():
    cofre = CofreDeTeste(DivisaoDeDados.por_percentual(serie_de_dias(dias=10)).teste)

    with pytest.raises(TesteProtegidoError, match="exige um motivo"):
        cofre.abrir("")
    with pytest.raises(TesteProtegidoError):
        cofre.abrir("   ")


def test_abrir_registra_motivo_e_horario():
    cofre = CofreDeTeste(DivisaoDeDados.por_percentual(serie_de_dias(dias=10)).teste)
    janela = cofre.abrir("medicao final")

    assert janela.particao is Particao.TEST
    assert cofre.vezes == 1
    assert cofre.aberturas[0].motivo == "medicao final"
    assert cofre.contaminado is False


def test_a_segunda_abertura_contamina_o_teste():
    cofre = CofreDeTeste(DivisaoDeDados.por_percentual(serie_de_dias(dias=10)).teste)
    cofre.abrir("primeira medicao")
    cofre.abrir("dei uma espiada depois de mexer no parametro")

    assert cofre.vezes == 2
    assert cofre.contaminado is True


# --- a barreira estrutural -----------------------------------------------------------------


def test_a_barreira_recusa_a_particao_test():
    with pytest.raises(TesteProtegidoError, match="nao avalia parametros sobre o TEST"):
        garantir_sem_teste([Particao.TRAIN, Particao.VALIDATION, Particao.TEST])


def test_a_barreira_deixa_passar_treino_e_validacao():
    garantir_sem_teste([Particao.TRAIN, Particao.VALIDATION])  # nao levanta


def test_a_barreira_tambem_olha_janelas():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=10))

    garantir_sem_teste([d.treino, d.validacao])
    with pytest.raises(TesteProtegidoError):
        garantir_sem_teste([d.treino, d.teste])
