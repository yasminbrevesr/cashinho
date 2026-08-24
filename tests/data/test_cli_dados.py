"""A CLI de market data."""

from __future__ import annotations

import json

import pytest

from cashinho.data.__main__ import main


def test_lista_os_providers(capsys):
    assert main(["--providers", "--sem-cor"]) == 0
    saida = capsys.readouterr().out

    assert "brapi" in saida
    assert "metatrader" in saida


def test_lista_em_json(capsys):
    main(["--providers", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["catalogo"]["brapi"]["disponivel"] is True
    assert dados["catalogo"]["metatrader"]["disponivel"] is True


def test_carrega_com_o_provedor_demo(capsys):
    assert main(["--ativo", "PETR4", "--timeframe", "1d", "--provider", "demo",
                 "--sem-cor"]) == 0
    saida = capsys.readouterr().out

    assert "ANALISE · PETR4" in saida
    assert "ORIGEM DO DADO" in saida
    assert "QUALIDADE DOS DADOS" in saida


def test_saida_em_json_traz_fonte_status_e_qualidade(capsys):
    main(["--ativo", "PETR4", "--timeframe", "1d", "--provider", "demo", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["fonte"] == "demo"
    assert "status" in dados and "qualidade" in dados
    assert dados["qualidade"]["valida"] is True


def test_finalidade_de_tempo_real_sem_provedor_sai_com_codigo(capsys):
    codigo = main(["--ativo", "PETR4", "--finalidade", "scanner_intradiario",
                   "--sem-cor"])
    saida = capsys.readouterr().out

    assert codigo == 2
    assert "NAO FOI POSSIVEL CARREGAR" in saida
    assert "tempo real" in saida


def test_provedor_desconhecido_e_recusado(capsys):
    codigo = main(["--provider", "bloomberg", "--sem-cor"])

    assert codigo == 2
    assert "desconhecido" in capsys.readouterr().out


def test_metatrader_sem_terminal_avisa_em_vez_de_cair_para_outro(capsys):
    """Sem fallback silencioso: nada de servir dado historico como realtime."""
    codigo = main(["--provider", "metatrader", "--ativo", "PETR4", "--sem-cor"])
    saida = capsys.readouterr().out

    assert codigo == 2
    assert "METATRADER NAO DISPONIVEL" in saida or "TERMINAL OFFLINE" in saida


def test_a_tela_mostra_os_dois_papeis(capsys):
    main(["--ativo", "PETR4", "--timeframe", "1d", "--provider", "demo", "--sem-cor"])
    saida = capsys.readouterr().out

    assert "MARKET DATA" in saida
    assert "Historical Provider" in saida
    assert "Realtime Provider" in saida
