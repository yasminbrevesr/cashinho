"""O Paper Trading na linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.broker.__main__ import carregar, main


def _rodar(argv, pasta, capsys):
    codigo = main(["--dados", str(pasta), "--sem-cor", *argv])
    return codigo, capsys.readouterr().out


def _conta(tmp_path, capsys, capital="50000"):
    _rodar(["--capital", capital, "reset"], tmp_path, capsys)
    _rodar(["preco", "PETR4", "31.00"], tmp_path, capsys)
    capsys.readouterr()


def test_status_mostra_a_pagina(tmp_path, capsys):
    _conta(tmp_path, capsys)
    codigo, saida = _rodar([], tmp_path, capsys)

    assert codigo == 0
    assert "PAPER TRADING" in saida
    assert "R$ 50.000,00" in saida


def test_compra_sem_stop_e_barrada_pelo_risco(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _, saida = _rodar(["comprar", "PETR4", "100"], tmp_path, capsys)

    assert "rejeitada" in saida
    assert "sem stop de referencia" in saida


def test_compra_com_stop_executa_e_persiste(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _, saida = _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)

    assert "executada" in saida
    broker = carregar(tmp_path, 50_000.0)
    assert broker.get_positions()[0].quantidade == 100


def test_o_preco_faz_as_ordens_dispararem(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)
    _rodar(["oco", "PETR4", "100", "--stop", "30.70", "--alvo", "31.60"], tmp_path, capsys)
    capsys.readouterr()

    _, saida = _rodar(["preco", "PETR4", "31.70"], tmp_path, capsys)

    assert "1 ordem(ns) executada(s)" in saida
    assert "take_profit" in saida


def test_oco_sem_posicao_avisa(tmp_path, capsys):
    _conta(tmp_path, capsys)
    codigo, saida = _rodar(["oco", "PETR4", "100", "--stop", "30.0", "--alvo", "32.0"],
                           tmp_path, capsys)

    assert codigo == 2
    assert "nao ha posicao aberta" in saida


def test_kill_switch_bloqueia_novas_operacoes(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _, saida = _rodar(["kill-switch", "on", "--motivo", "fim do expediente"], tmp_path, capsys)

    assert "KILL SWITCH ACIONADO" in saida

    _, depois = _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)
    assert "rejeitada" in depois
    assert "kill switch" in depois


def test_kill_switch_pode_ser_liberado(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _rodar(["kill-switch", "on"], tmp_path, capsys)
    _rodar(["kill-switch", "off"], tmp_path, capsys)
    capsys.readouterr()

    _, saida = _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)
    assert "executada" in saida


def test_cancelar_todas(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _rodar(["comprar", "PETR4", "100", "--tipo", "limit", "--preco", "30.0",
            "--stop", "29.5"], tmp_path, capsys)
    capsys.readouterr()

    _, saida = _rodar(["cancelar", "--todas"], tmp_path, capsys)
    assert "1 ordem(ns) cancelada(s)" in saida


def test_cancelar_id_desconhecido_avisa(tmp_path, capsys):
    _conta(tmp_path, capsys)
    codigo, saida = _rodar(["cancelar", "ord-nao-existe"], tmp_path, capsys)

    assert codigo == 2
    assert "nao foi possivel cancelar" in saida


def test_saida_em_json(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)
    capsys.readouterr()

    _, saida = _rodar(["--json"], tmp_path, capsys)
    dados = json.loads(saida)

    assert dados["saldo"]["patrimonio"] > 0
    assert len(dados["posicoes"]) == 1


def test_reset_zera_a_conta(tmp_path, capsys):
    _conta(tmp_path, capsys)
    _rodar(["comprar", "PETR4", "100", "--stop", "30.70"], tmp_path, capsys)
    capsys.readouterr()

    _rodar(["--capital", "80000", "reset"], tmp_path, capsys)
    broker = carregar(tmp_path, 80_000.0)

    assert broker.get_positions() == []
    assert broker.get_balance().saldo == 80_000.0


def test_opcoes_globais_funcionam_antes_e_depois_do_subcomando(tmp_path, capsys):
    _conta(tmp_path, capsys)

    a, _ = _rodar(["status"], tmp_path, capsys)
    b = main(["--dados", str(tmp_path), "status", "--sem-cor"])
    capsys.readouterr()

    assert a == 0 and b == 0


def test_tipo_de_ordem_invalido_e_recusado(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dados", str(tmp_path), "comprar", "PETR4", "100", "--tipo", "magica"])
