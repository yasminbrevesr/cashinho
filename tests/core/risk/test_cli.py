"""A pagina na linha de comando: configurar, simular e travar."""

from __future__ import annotations

import json

import pytest

from cashinho.core.risk.__main__ import carregar, main


def _rodar(argv, pasta):
    return main(["--dados", str(pasta), "--sem-cor", *argv])


def test_status_por_padrao(tmp_path, capsys):
    codigo = _rodar([], tmp_path)

    assert codigo == 0
    assert "TRADING LIBERADO" in capsys.readouterr().out


def test_configurar_persiste_os_limites(tmp_path, capsys):
    _rodar(["configurar", "--capital", "40000", "--risco-trade", "0.5",
            "--perda-diaria", "2", "--max-trades", "3", "--exposicao-max", "50"], tmp_path)
    capsys.readouterr()

    rm = carregar(tmp_path)
    assert rm.config.capital == 40_000
    assert rm.config.risco_por_trade_pct == 0.5
    assert rm.config.perda_max_diaria_pct == 2.0
    assert rm.config.max_trades_dia == 3
    assert rm.config.exposicao_max_total_pct == 50.0


def test_configuracao_invalida_nao_e_gravada(tmp_path, capsys):
    _rodar(["configurar", "--capital", "10000"], tmp_path)
    capsys.readouterr()

    codigo = _rodar(["configurar", "--capital", "-5"], tmp_path)
    saida = capsys.readouterr().out

    assert codigo == 1
    assert "recusada" in saida
    assert carregar(tmp_path).config.capital == 10_000


def test_simular_mostra_a_decisao(tmp_path, capsys):
    _rodar(["configurar", "--capital", "100000"], tmp_path)
    capsys.readouterr()

    _rodar(["simular", "PETR4", "compra", "31.00", "30.70"], tmp_path)
    saida = capsys.readouterr().out

    assert "APROVADO PELO RISCO" in saida
    assert "PETR4" in saida


def test_simular_ordem_invalida_mostra_rejeicao(tmp_path, capsys):
    _rodar(["simular", "PETR4", "compra", "31.00", "31.00"], tmp_path)
    saida = capsys.readouterr().out

    assert "REJEITADO PELO RISCO" in saida
    assert "mesmo preco" in saida


def test_kill_switch_liga_e_desliga(tmp_path, capsys):
    codigo = _rodar(["kill-switch", "on", "--motivo", "fim do expediente"], tmp_path)
    saida = capsys.readouterr().out

    assert codigo == 1  # sai com erro: o robo esta travado
    assert "TRADING BLOQUEADO" in saida
    assert "fim do expediente" in saida

    codigo = _rodar(["kill-switch", "off"], tmp_path)
    assert codigo == 0
    assert "TRADING LIBERADO" in capsys.readouterr().out


def test_estado_sobrevive_entre_chamadas(tmp_path, capsys):
    _rodar(["kill-switch", "on"], tmp_path)
    capsys.readouterr()

    assert carregar(tmp_path).estado.kill_switch is not None
    assert json.loads((tmp_path / "risco-estado.json").read_text())["kill_switch"]["codigo"] == "manual"


def test_novo_pregao_zera_o_dia(tmp_path, capsys):
    _rodar(["novo-pregao"], tmp_path)
    saida = capsys.readouterr().out

    assert "contadores do dia zerados" in saida
    assert carregar(tmp_path).estado.trades_dia == 0


def test_direcao_invalida_e_recusada(tmp_path):
    with pytest.raises(SystemExit):
        _rodar(["simular", "PETR4", "talvez", "31.00", "30.70"], tmp_path)
