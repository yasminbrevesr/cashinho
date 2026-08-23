"""A pagina de validacao e a linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.validacao import (
    Candidato,
    Ciclo,
    CofreDeTeste,
    DivisaoDeDados,
    Particao,
    RelatorioDeValidacao,
    ResultadoWalkForward,
    pagina,
    pagina_walk_forward,
    secao_alertas,
    secao_cofre,
    tabela_particoes,
)
from cashinho.core.validacao.__main__ import main

from .factories import medidas, serie_de_dias


@pytest.fixture
def relatorio():
    d = DivisaoDeDados.por_percentual(serie_de_dias(dias=12))
    cofre = CofreDeTeste(d.teste)
    cofre.abrir("medicao final")
    return RelatorioDeValidacao(
        d,
        [medidas(Particao.TRAIN, retorno=8.0, trades=40),
         medidas(Particao.VALIDATION, retorno=1.0, trades=12),
         medidas(Particao.TEST, retorno=-1.0, trades=10)],
        cofre=cofre, candidato="baseline",
    )


# --- a tabela pedida: train x validation x test ---------------------------------


def test_a_tabela_mostra_as_tres_particoes(relatorio):
    texto = tabela_particoes(relatorio)

    for rotulo in ("TRAIN", "VALIDATION", "TEST"):
        assert rotulo in texto


def test_a_tabela_mostra_as_seis_medidas(relatorio):
    texto = tabela_particoes(relatorio).upper()

    for coluna in ("RETORNO", "DRAWDOWN", "PF", "SHARPE", "EXPECTANCY", "TRADES"):
        assert coluna in texto


def test_a_pagina_mostra_alertas_de_degradacao(relatorio):
    texto = pagina(relatorio)

    assert "ALERTAS" in texto
    assert "retorno" in texto.lower()


def test_a_pagina_mostra_o_veredito(relatorio):
    assert relatorio.veredito in pagina(relatorio)


def test_a_pagina_mostra_as_aberturas_do_cofre(relatorio):
    texto = secao_cofre(relatorio.cofre)

    assert "medicao final" in texto
    assert "1 vez" in texto


def test_sem_alertas_a_secao_diz_isso():
    assert secao_alertas([]).strip() != ""


def test_a_pagina_lembra_para_que_serve_a_validacao(relatorio):
    assert "NAO funciona" in pagina(relatorio)


def test_a_pagina_aceita_cores(relatorio):
    assert "\x1b[" in pagina(relatorio, cores=True)
    assert "\x1b[" not in pagina(relatorio, cores=False)


def test_pagina_de_walk_forward():
    from .test_walkforward import ciclo

    texto = pagina_walk_forward(ResultadoWalkForward([ciclo(1, 2.0), ciclo(2, -1.0)]))

    assert "WALK-FORWARD" in texto
    assert "CONSISTENCIA" in texto


# --- a linha de comando ----------------------------------------------------------------
#
# a base precisa ser 1m (e o que o gatilho do pipeline le), e o pipeline roda
# candle a candle: por isso as series destes testes sao curtas


def test_cli_roda_a_validacao(capsys):
    assert main(["--dias", "12", "--semente", "5"]) == 0
    saida = capsys.readouterr().out

    assert "TRAIN" in saida and "TEST" in saida


def test_cli_em_json(capsys):
    assert main(["--dias", "12", "--json"]) == 0
    dados = json.loads(capsys.readouterr().out)

    assert set(dados) >= {"medidas", "alertas", "veredito", "cofre"}


def test_cli_com_sem_teste_deixa_o_cofre_fechado(capsys):
    main(["--dias", "12", "--sem-teste", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["cofre"]["vezes_aberto"] == 0
    assert all(m["particao"] != "test" for m in dados["medidas"])


def test_cli_aceita_percentuais(capsys):
    main(["--dias", "8", "--percentuais", "0.5,0.25,0.25", "--json"])
    dados = json.loads(capsys.readouterr().out)

    treino = dados["divisao"]["janelas"][0]
    assert treino["particao"] == "train" and treino["dias"] == 4


def test_cli_recusa_percentuais_que_nao_somam_um_nem_cem():
    with pytest.raises(SystemExit):
        main(["--percentuais", "0.5,0.5,0.5"])


def test_cli_aceita_percentuais_em_porcentagem(capsys):
    main(["--dias", "8", "--percentuais", "50,25,25", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["divisao"]["janelas"][0]["dias"] == 4


def test_cli_walk_forward(capsys):
    assert main(["--dias", "12", "--walk-forward", "--treino", "5", "--teste", "3"]) == 0
    saida = capsys.readouterr().out

    assert "WALK-FORWARD" in saida
    assert "CONSISTENCIA" in saida


def test_cli_walk_forward_em_json(capsys):
    main(["--dias", "12", "--walk-forward", "--treino", "5", "--teste", "3", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert set(dados) >= {"ciclos", "consistencia", "veredito"}


def test_cli_recusa_base_que_nao_gera_o_gatilho(capsys):
    """--timeframe 5m saia com mensagem, nao com traceback do motor mtf."""
    assert main(["--dias", "3", "--timeframe", "5m"]) == 2
    assert "gatilho" in capsys.readouterr().out


def test_cli_com_serie_curta_nao_quebra(capsys):
    codigo = main(["--dias", "3", "--walk-forward", "--treino", "10", "--teste", "5"])
    saida = capsys.readouterr().out

    assert codigo == 0
    assert "ciclo" in saida.lower()
