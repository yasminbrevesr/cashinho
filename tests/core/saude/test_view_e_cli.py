"""A tela SYSTEM HEALTH e a linha de comando."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.saude import (
    EstadoDeSaude,
    Modo,
    faixa_de_operacao,
    linha_resumo,
    pagina,
    secao_erros,
)
from cashinho.core.saude.__main__ import main

from .factories import AGORA, monitor, paper, risco, telemetria


def saude(atraso: float = 1.0, **campos):
    t = telemetria(AGORA, market_data_min=atraso)
    m = monitor(t=t, **campos)
    m.registrar_analise(AGORA - timedelta(minutes=3))
    return m.verificar()


# --- a tela -------------------------------------------------------------------


def test_a_tela_lista_os_sete_componentes():
    texto = pagina(saude())

    for nome in ("Market Data", "Database", "Scanner", "Paper Broker",
                 "News", "Backtest Engine", "Risk Manager"):
        assert nome in texto


def test_a_tela_mostra_os_tres_estados():
    texto = pagina(saude(broker=paper(), risco=risco()))

    assert "ONLINE" in texto
    assert "OFFLINE" in texto
    assert "DEGRADED" in texto


def test_a_tela_mostra_o_que_foi_pedido():
    texto = pagina(saude(broker=paper(), risco=risco()))

    assert "ULTIMO SINAL" in texto
    assert "LATENCIA" in texto
    assert "ERROS" in texto
    assert "modo atual" in texto
    assert "kill switch" in texto
    assert "ultima analise" in texto


def test_a_faixa_avisa_quando_as_operacoes_estao_bloqueadas():
    assert "OPERACOES BLOQUEADAS" in faixa_de_operacao(saude(atraso=30))
    assert "OPERACOES LIBERADAS" in faixa_de_operacao(saude(atraso=1))


def test_o_motivo_do_bloqueio_aparece_na_tela():
    texto = pagina(saude(atraso=30))

    assert "Market Data OFFLINE" in texto
    assert "nao serve para decidir" in texto


def test_o_kill_switch_aparece_acionado():
    r = risco()
    r.acionar_kill_switch("perda diaria")

    assert "ACIONADO" in pagina(saude(risco=r))


def test_a_latencia_sai_legivel():
    texto = pagina(saude())

    assert "ms" in texto or "s" in texto


def test_erros_recentes_aparecem_com_hora_e_componente():
    t = telemetria(AGORA, market_data_min=1)
    t.erro("news", "timeout ao ler a agenda")
    texto = pagina(monitor(t=t).verificar())

    assert "ERROS RECENTES" in texto
    assert "timeout ao ler a agenda" in texto
    assert "news" in texto


def test_sem_erros_a_secao_diz_isso():
    assert "nenhum erro" in secao_erros((), AGORA)


def test_a_tela_aceita_cores():
    assert "\x1b[" in pagina(saude(), cores=True)
    assert "\x1b[" not in pagina(saude(), cores=False)


def test_o_resumo_cabe_em_uma_linha():
    resumo = linha_resumo(saude(broker=paper(), risco=risco()))

    assert "\n" not in resumo
    assert "SAUDE" in resumo


def test_o_resumo_aponta_os_componentes_com_problema():
    assert "atencao" in linha_resumo(saude(atraso=30))


# --- a linha de comando ---------------------------------------------------------


def test_cli_mostra_o_painel(capsys):
    codigo = main(["--fonte", "demo", "--sem-cor"])
    saida = capsys.readouterr().out

    assert "SYSTEM HEALTH" in saida
    assert "Market Data" in saida
    assert codigo in (0, 2)


def test_cli_em_json(capsys):
    main(["--fonte", "demo", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert len(dados["componentes"]) == 7
    assert set(dados) >= {"estado_geral", "modo", "kill_switch", "ultima_analise",
                          "bloqueia_novas_operacoes"}


def test_cli_devolve_codigo_2_quando_bloqueado(capsys):
    """Da para usar em script: codigo diferente de zero quando nao da para operar."""
    codigo = main(["--fonte", "nenhuma", "--sem-cor"])

    assert codigo == 2
    assert "OPERACOES BLOQUEADAS" in capsys.readouterr().out


def test_cli_sem_fonte_marca_market_data_offline(capsys):
    main(["--fonte", "nenhuma", "--json"])
    dados = json.loads(capsys.readouterr().out)

    md = next(c for c in dados["componentes"] if c["chave"] == "market_data")
    assert md["estado"] == "OFFLINE"
    assert dados["bloqueia_novas_operacoes"] is True


def test_cli_le_o_diario_quando_informado(tmp_path, capsys):
    caminho = tmp_path / "diario.jsonl"
    caminho.write_text('{"a": 1}\n', encoding="utf-8")

    main(["--fonte", "demo", "--diario", str(caminho), "--json"])
    dados = json.loads(capsys.readouterr().out)

    banco = next(c for c in dados["componentes"] if c["chave"] == "database")
    assert banco["estado"] == "ONLINE"
    assert "1 registro" in banco["detalhe"]


def test_cli_le_a_agenda_quando_informada(tmp_path, capsys):
    from .factories import AGORA

    caminho = tmp_path / "eventos.json"
    caminho.write_text(json.dumps({
        "atualizado_em": AGORA.isoformat(), "fonte": "manual", "eventos": [],
    }), encoding="utf-8")

    main(["--fonte", "demo", "--eventos", str(caminho), "--json"])
    dados = json.loads(capsys.readouterr().out)

    news = next(c for c in dados["componentes"] if c["chave"] == "news")
    assert news["estado"] in ("ONLINE", "DEGRADED")


def test_cli_aceita_o_modo(capsys):
    main(["--fonte", "demo", "--modo", "paper", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["modo"] == "PAPER TRADING"
