"""O Diario na linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.diario.__main__ import main

from .factories import BASE, diario


@pytest.fixture()
def arquivo(tmp_path):
    return diario().salvar(tmp_path / "diario.jsonl")


def _rodar(argv, arquivo, capsys):
    codigo = main(["--arquivo", str(arquivo), "--sem-cor", *argv])
    return codigo, capsys.readouterr().out


def test_pagina_padrao(arquivo, capsys):
    codigo, saida = _rodar([], arquivo, capsys)

    assert codigo == 0
    assert "DIARIO DE TRADES" in saida
    assert "POR SETUP" in saida


def test_filtro_por_ativo(arquivo, capsys):
    _, saida = _rodar(["--ativo", "PETR4"], arquivo, capsys)

    assert "PETR4" in saida
    assert "3 de 5 operacoes" in saida


def test_filtro_por_resultado(arquivo, capsys):
    _, saida = _rodar(["--resultado", "perdedor"], arquivo, capsys)

    assert "2 de 5 operacoes" in saida


def test_filtro_por_periodo(arquivo, capsys):
    dia = BASE.date().isoformat()
    _, saida = _rodar(["--de", dia, "--ate", dia], arquivo, capsys)

    assert "2 de 5 operacoes" in saida


def test_filtro_por_setup_e_timeframe(arquivo, capsys):
    _, saida = _rodar(["--setup", "rompimento", "--timeframe", "5m"], arquivo, capsys)

    assert "rompimento" in saida


def test_data_invalida_e_recusada(arquivo):
    with pytest.raises(SystemExit):
        main(["--arquivo", str(arquivo), "--de", "20-08-2026"])


def test_escolha_de_agrupamentos(arquivo, capsys):
    _, saida = _rodar(["--grupos", "setup,dia"], arquivo, capsys)

    assert "POR SETUP" in saida
    assert "POR DIA DA SEMANA" in saida
    assert "POR ATIVO" not in saida


def test_saida_em_json(arquivo, capsys):
    _, saida = _rodar(["--json"], arquivo, capsys)
    dados = json.loads(saida)

    assert dados["total_de_registros"] == 5
    assert "agrupamentos" in dados


def test_detalhe_de_uma_operacao(arquivo, capsys):
    dados = json.loads(_rodar(["--json"], arquivo, capsys)[1])
    alvo = dados["registros"][0]["id"]

    codigo, saida = _rodar(["--detalhe", alvo], arquivo, capsys)

    assert codigo == 0
    assert "MOTIVO DA ENTRADA" in saida


def test_detalhe_de_id_desconhecido(arquivo, capsys):
    codigo, saida = _rodar(["--detalhe", "reg-nao-existe"], arquivo, capsys)

    assert codigo == 2
    assert "nao encontrada" in saida


def test_diario_vazio_nao_e_erro(tmp_path, capsys):
    codigo, saida = _rodar([], tmp_path / "vazio.jsonl", capsys)

    assert codigo == 0
    assert "o diario esta vazio" in saida
