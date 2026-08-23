"""O Market Replay na linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.replay.__main__ import main

BASE = ["--ativo", "PETR4", "--semente", "3", "--dias", "3", "--sem-cor"]


def _rodar(argv, capsys):
    codigo = main([*BASE, *argv])
    return codigo, capsys.readouterr().out


def test_replay_padrao_roda_sem_rede(capsys):
    codigo, saida = _rodar(["--passos", "80"], capsys)

    assert codigo == 0
    assert "MARKET REPLAY" in saida
    assert "dados sinteticos" in saida


def test_as_quatro_escolhas_aparecem_no_cabecalho(capsys):
    _, saida = _rodar(["--data", "2026-08-20", "--timeframe", "1m",
                       "--velocidade", "maxima", "--passos", "50"], capsys)

    assert "PETR4" in saida
    assert "20/08/2026" in saida
    assert "1m" in saida
    assert "maxima" in saida


def test_listar_dias(capsys):
    codigo, saida = _rodar(["--listar-dias"], capsys)

    assert codigo == 0
    assert "pregoes disponiveis" in saida
    assert "candles" in saida


def test_dia_inexistente_avisa_e_lista(capsys):
    codigo, saida = _rodar(["--data", "2027-01-01"], capsys)

    assert codigo == 2
    assert "nao ha candles" in saida
    assert "disponiveis" in saida


def test_velocidade_invalida_e_recusada():
    with pytest.raises(SystemExit):
        main([*BASE, "--velocidade", "turbo"])


def test_data_invalida_e_recusada():
    with pytest.raises(SystemExit):
        main([*BASE, "--data", "20-08-2026"])


def test_saida_em_json(capsys):
    _, saida = _rodar(["--passos", "120", "--json"], capsys)
    dados = json.loads(saida)

    assert dados["replay"]["symbol"] == "PETR4"
    assert "conta" in dados and "diario" in dados


def test_limite_de_passos(capsys):
    _, saida = _rodar(["--passos", "40", "--json"], capsys)
    dados = json.loads(saida)

    assert dados["replay"]["passos"] == 40


def test_acompanhar_redesenha_a_tela(capsys):
    _, saida = _rodar(["--passos", "100", "--acompanhar", "25"], capsys)

    assert saida.count("MARKET REPLAY") >= 3


def test_pasta_de_csv_inexistente_falha_com_mensagem(capsys):
    codigo, saida = _rodar(["--fonte", "csv", "--pasta", "/tmp/pasta-inexistente-replay"], capsys)

    assert codigo == 2
    assert "nao foi possivel carregar" in saida
