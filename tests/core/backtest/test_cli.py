"""A pagina Backtest na linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.backtest.__main__ import main


def _rodar(argv, capsys):
    codigo = main([*argv, "--sem-cor"])
    return codigo, capsys.readouterr().out


def test_roda_com_a_fonte_demo_sem_precisar_de_rede(capsys):
    codigo, saida = _rodar(["--ativo", "PETR4", "--dias", "5"], capsys)

    assert codigo == 0
    assert "BACKTEST · PETR4" in saida
    assert "CURVA DE CAPITAL" in saida
    assert "dados sinteticos" in saida  # a pagina avisa que nao e' mercado


def test_parametros_da_pagina_chegam_no_resultado(capsys):
    _, saida = _rodar(
        ["--ativo", "VALE3", "--dias", "5", "--capital", "50000", "--timeframe", "15m",
         "--risco-trade", "0.5", "--max-trades", "2", "--spread", "2", "--slippage", "1",
         "--corretagem", "4.90", "--taxas", "0.05"],
        capsys,
    )

    assert "VALE3" in saida
    assert "15m" in saida
    assert "R$ 50.000,00" in saida


def test_saida_em_json_e_valida(capsys):
    _, saida = _rodar(["--dias", "5", "--json"], capsys)
    dados = json.loads(saida)

    assert dados["symbol"] == "PETR4"
    assert "metricas" in dados and "trades" in dados


def test_resumo_cabe_em_uma_linha(capsys):
    _, saida = _rodar(["--dias", "5", "--resumo"], capsys)

    assert len([l for l in saida.strip().splitlines() if l]) == 1
    assert "retorno" in saida


def test_semente_diferente_muda_a_serie(capsys):
    _, um = _rodar(["--dias", "5", "--semente", "1", "--resumo"], capsys)
    _, dois = _rodar(["--dias", "5", "--semente", "2", "--resumo"], capsys)

    assert um != dois


def test_mesma_semente_repete_o_resultado(capsys):
    _, um = _rodar(["--dias", "5", "--semente", "7", "--resumo"], capsys)
    _, dois = _rodar(["--dias", "5", "--semente", "7", "--resumo"], capsys)

    assert um == dois


def test_estrategia_desconhecida_avisa_e_lista_as_disponiveis(capsys):
    codigo, saida = _rodar(["--estrategia", "nao-existe"], capsys)

    assert codigo == 2
    assert "baseline-tendencia" in saida


def test_csv_inexistente_falha_com_mensagem(capsys):
    codigo, saida = _rodar(["--fonte", "csv", "--pasta", "/tmp/pasta-que-nao-existe-cashinho"], capsys)

    assert codigo == 2
    assert "nao foi possivel carregar" in saida


def test_data_invalida_e_recusada():
    with pytest.raises(SystemExit):
        main(["--inicio", "20-08-2026"])


def test_comparar_timeframes_pela_linha_de_comando(capsys):
    codigo, saida = _rodar(["--comparar", "--dias", "5", "--timeframes", "5m,15m"], capsys)

    assert codigo == 0
    assert "COMPARAR TIMEFRAMES" in saida
    assert "TABELA COMPARATIVA" in saida
    assert "VEREDITO" in saida
    assert "5m" in saida and "15m" in saida


def test_comparar_em_json(capsys):
    _, saida = _rodar(["--comparar", "--dias", "5", "--timeframes", "5m,15m", "--json"], capsys)
    dados = json.loads(saida)

    assert dados["symbol"] == "PETR4"
    assert [l["timeframe"] for l in dados["linhas"]] == ["5m", "15m"]
    assert "veredito" in dados


def test_comparar_aceita_1h_como_60m(capsys):
    _, saida = _rodar(["--comparar", "--dias", "5", "--timeframes", "1h", "--json"], capsys)
    dados = json.loads(saida)

    assert dados["linhas"][0]["timeframe"] == "60m"
