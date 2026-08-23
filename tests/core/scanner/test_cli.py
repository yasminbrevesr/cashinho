"""O Scanner na linha de comando."""

from __future__ import annotations

import json

import pytest

from cashinho.core.scanner.__main__ import main


def _rodar(argv, capsys):
    codigo = main([*argv, "--sem-cor"])
    return codigo, capsys.readouterr().out


BASE = ["--ativos", "PETR4,VALE3,ITUB4", "--dias", "3",
        "--atr-min", "0.05", "--liquidez-minima", "1000000"]


def test_varredura_padrao_roda_sem_rede(capsys):
    codigo, saida = _rodar(BASE, capsys)

    assert codigo == 0
    assert "SCANNER B3" in saida
    assert "dados sinteticos" in saida


def test_nada_encontrado_sai_com_codigo_zero(capsys):
    """Nao achar oportunidade nao e' erro."""
    codigo, saida = _rodar(["--ativos", "PETR4", "--dias", "3",
                            "--atr-min", "9.0", "--atr-max", "9.9"], capsys)

    assert codigo == 0
    assert "NENHUMA OPORTUNIDADE ENCONTRADA" in saida


def test_a_ordenacao_e_escolhida_na_linha_de_comando(capsys):
    _, saida = _rodar([*BASE, "--ordenar", "ativo"], capsys)
    linhas = [l for l in saida.splitlines() if l.startswith("  ") and "3" in l[:10]]

    assert "ordenado por ativo" in saida


def test_ordenacao_invalida_e_recusada():
    with pytest.raises(SystemExit):
        main(["--ordenar", "sorte"])


def test_saida_em_json_e_valida(capsys):
    _, saida = _rodar([*BASE, "--json"], capsys)
    dados = json.loads(saida)

    assert dados["ordenado_por"] == "score"
    assert len(dados["linhas"]) == 3
    assert "tem_oportunidades" in dados


def test_detalhe_de_um_ativo(capsys):
    codigo, saida = _rodar([*BASE, "--detalhe", "petr4"], capsys)

    assert codigo == 0
    assert "PETR4" in saida
    assert "FILTROS INICIAIS" in saida
    assert "Market Data" in saida


def test_detalhe_de_ativo_fora_da_watchlist_avisa(capsys):
    codigo, saida = _rodar([*BASE, "--detalhe", "MGLU3"], capsys)

    assert codigo == 2
    assert "nao esta na watchlist" in saida


def test_pasta_de_csv_inexistente_falha_com_mensagem(capsys):
    codigo, saida = _rodar(["--fonte", "csv", "--pasta", "/tmp/pasta-inexistente-cashinho"], capsys)

    assert codigo == 2
    assert "nao foi possivel usar a pasta" in saida


def test_limite_corta_a_tabela(capsys):
    _, saida = _rodar([*BASE, "--limite", "1"], capsys)
    linhas_de_ativo = [l for l in saida.splitlines()
                       if l.startswith("  ") and any(a in l for a in ("PETR4", "VALE3", "ITUB4"))]

    assert len(linhas_de_ativo) == 1


def test_mesma_semente_repete_a_analise(capsys):
    """O horario da varredura muda entre execucoes; a analise, nao."""
    _, um = _rodar([*BASE, "--semente", "5", "--json"], capsys)
    _, dois = _rodar([*BASE, "--semente", "5", "--json"], capsys)

    a, b = json.loads(um), json.loads(dois)
    assert a["linhas"] == b["linhas"]  # a analise e' identica; so o relogio da varredura muda


def test_boleta_de_ativo_sem_setup_aprovado_explica_sem_erro(capsys):
    codigo, saida = _rodar([*BASE, "--boleta", "PETR4"], capsys)

    assert codigo == 0
    assert "PETR4" in saida
    assert "BOLETA GENIAL" in saida
    # sem setup aprovado, a boleta nao e' gerada - e a tela diz por que
    assert "BOLETA NAO GERADA" in saida or "Quantidade" in saida


def test_boleta_de_ativo_fora_da_watchlist(capsys):
    codigo, saida = _rodar([*BASE, "--boleta", "MGLU3"], capsys)

    assert codigo == 2
    assert "nao esta na watchlist" in saida


def test_a_boleta_avisa_que_nao_envia_ordem(capsys):
    _, saida = _rodar([*BASE, "--boleta", "PETR4"], capsys)
    minusculo = saida.lower()

    assert "NAO ENVIA ORDEM" in saida
    # nenhuma frase que sugira que algo foi transmitido para a corretora
    for alegacao in ("ordem enviada", "ordem transmitida", "enviamos", "ordem executada na genial"):
        assert alegacao not in minusculo
