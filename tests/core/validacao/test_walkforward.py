"""Walk-forward: a mesma pergunta repetida ao longo do tempo."""

from __future__ import annotations

import pytest

from cashinho.core.oportunidade import EstrategiaOportunidade
from cashinho.core.validacao import (
    Ciclo,
    ConfigWalkForward,
    DivisaoInvalidaError,
    Particao,
    ResultadoWalkForward,
    ValidadorDeEstrategia,
    janelas_walk_forward,
    walk_forward,
)

from .factories import config_validacao, medidas, serie_de_dias


def janela_falsa(particao, serie):
    from cashinho.core.validacao.divisao import _janela, dias_da_serie

    return _janela(serie, particao, dias_da_serie(serie))


def ciclo(indice, retorno, trades=5):
    serie = serie_de_dias(dias=3)
    j = janela_falsa(Particao.TRAIN, serie)
    return Ciclo(indice, j, j, medidas(Particao.TRAIN),
                 medidas(Particao.VALIDATION, retorno=retorno, trades=trades))


# --- as janelas andam para a frente ------------------------------------------


def test_as_janelas_andam_o_tamanho_do_teste():
    serie = serie_de_dias(dias=25)  # 10 + 5, andando de 5 em 5: comeca em 0, 5 e 10
    pares = janelas_walk_forward(serie, ConfigWalkForward(dias_de_treino=10, dias_de_teste=5))

    assert len(pares) == 3
    assert [t.dias for t, _ in pares] == [10, 10, 10]
    assert [te.dias for _, te in pares] == [5, 5, 5]


def test_o_teste_de_cada_ciclo_vem_depois_do_treino():
    serie = serie_de_dias(dias=20)
    for treino, teste in janelas_walk_forward(serie, ConfigWalkForward(10, 5)):
        assert treino.fim < teste.inicio


def test_as_janelas_de_treino_avancam_no_tempo():
    serie = serie_de_dias(dias=20)
    pares = janelas_walk_forward(serie, ConfigWalkForward(10, 5))
    inicios = [t.inicio for t, _ in pares]

    assert inicios == sorted(inicios)
    assert len(set(inicios)) == len(inicios)


def test_o_passo_e_configuravel():
    serie = serie_de_dias(dias=20)
    passo_curto = janelas_walk_forward(serie, ConfigWalkForward(10, 5, passo=2))
    passo_padrao = janelas_walk_forward(serie, ConfigWalkForward(10, 5))

    assert len(passo_curto) > len(passo_padrao)


def test_serie_curta_para_as_janelas_pedidas_e_recusada():
    with pytest.raises(DivisaoInvalidaError, match="pregoes"):
        janelas_walk_forward(serie_de_dias(dias=8), ConfigWalkForward(10, 5))


def test_janela_invalida_e_recusada_na_configuracao():
    with pytest.raises(DivisaoInvalidaError):
        ConfigWalkForward(dias_de_treino=0, dias_de_teste=5)
    with pytest.raises(DivisaoInvalidaError):
        ConfigWalkForward(10, 5, passo=0)


def test_o_walk_forward_nao_usa_a_particao_test():
    """O TEST guardado no cofre nao entra nos ciclos."""
    serie = serie_de_dias(dias=20)
    for treino, teste in janelas_walk_forward(serie, ConfigWalkForward(10, 5)):
        assert treino.particao is Particao.TRAIN
        assert teste.particao is not Particao.TEST


# --- o que os ciclos dizem juntos -----------------------------------------------


def test_consistencia_conta_os_ciclos_que_se_sustentaram():
    r = ResultadoWalkForward([ciclo(1, 2.0), ciclo(2, -1.0), ciclo(3, 1.0), ciclo(4, 0.5)])

    assert r.sustentaram == 3
    assert r.consistencia == 0.75
    assert "3 de 4" in r.veredito


def test_ciclo_sem_trades_nao_conta_como_sustentado():
    assert ciclo(1, 0.0, trades=0).sustentou is False


def test_maioria_de_ciclos_ruins_muda_o_veredito():
    r = ResultadoWalkForward([ciclo(1, 2.0), ciclo(2, -1.0), ciclo(3, -1.0), ciclo(4, -2.0)])

    assert "nao se repete" in r.veredito


def test_poucos_ciclos_nao_viram_conclusao():
    r = ResultadoWalkForward([ciclo(1, 5.0), ciclo(2, 4.0)])

    assert r.consistencia == 1.0
    assert "poucos para falar em consistencia" in r.veredito


def test_sem_ciclos_o_resultado_e_honesto():
    r = ResultadoWalkForward()

    assert r.total == 0 and r.consistencia == 0.0
    assert "nenhum ciclo" in r.veredito


# --- rodando de verdade -------------------------------------------------------------


def test_roda_os_ciclos_sobre_a_serie():
    serie = serie_de_dias(dias=20)
    v = ValidadorDeEstrategia(EstrategiaOportunidade, config_validacao())

    r = walk_forward(v, serie, ConfigWalkForward(dias_de_treino=8, dias_de_teste=4))

    assert r.total == 3
    assert all(c.medida_teste.dias == 4 for c in r.ciclos)


def test_serie_curta_vira_aviso_e_nao_excecao():
    v = ValidadorDeEstrategia(EstrategiaOportunidade, config_validacao())
    r = walk_forward(v, serie_de_dias(dias=6), ConfigWalkForward(10, 5))

    assert r.total == 0
    assert any("pregoes" in a for a in r.avisos)


def test_avisa_quando_ha_poucos_trades_fora_da_amostra():
    serie = serie_de_dias(dias=20)
    v = ValidadorDeEstrategia(EstrategiaOportunidade, config_validacao())

    r = walk_forward(v, serie, ConfigWalkForward(8, 4))

    if r.trades_fora < 30:
        assert any("amostra pequena" in a for a in r.avisos)


def test_o_resultado_serializa_para_json():
    import json

    json.dumps(ResultadoWalkForward([ciclo(1, 1.0)]).para_dict())
