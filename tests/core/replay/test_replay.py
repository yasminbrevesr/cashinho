"""O motor do replay e o que ele produz."""

from __future__ import annotations

import json
from datetime import date

import pytest

from cashinho.core.replay import (
    MarketReplay,
    PassoReplay,
    ReplayConfig,
    TipoEvento,
    Velocidade,
)
from cashinho.core.replay.velocidade import Relogio

from .factories import DIA, pregao, replay, serie_alta


# --- o que o usuario escolhe -----------------------------------------------------


def test_a_configuracao_cobre_as_quatro_escolhas():
    cfg = ReplayConfig(symbol="VALE3", dia=DIA, timeframe_base="5m",
                       velocidade=Velocidade.X10)

    assert cfg.symbol == "VALE3"
    assert cfg.dia == DIA
    assert cfg.timeframe_base == "5m"
    assert cfg.velocidade is Velocidade.X10


def test_capital_invalido_e_recusado():
    with pytest.raises(ValueError):
        ReplayConfig(capital=0)


# --- reproducao cronologica ---------------------------------------------------------


def test_os_candles_saem_em_ordem():
    r = replay(serie_alta(n=60))
    instantes = [p.instante for p in r]

    assert instantes == sorted(instantes)
    assert len(instantes) == 60


def test_o_passo_devolve_o_candle_atual():
    r = replay(serie_alta(n=20))
    passo = r.passo()

    assert passo.indice == 0
    assert passo.candle is r.fita.atual


def test_executar_vai_ate_o_fim():
    r = replay(serie_alta(n=45))
    estado = r.executar()

    assert estado.passos == 45
    assert r.fita.terminou
    assert estado.progresso == pytest.approx(1.0)


def test_executar_pode_parar_antes():
    r = replay(serie_alta(n=60))
    estado = r.executar(ate=10)

    assert estado.passos == 10
    assert not r.fita.terminou


def test_o_callback_recebe_cada_passo():
    vistos: list[PassoReplay] = []
    r = replay(serie_alta(n=15))
    r.executar(aoPasso=vistos.append)

    assert len(vistos) == 15
    assert all(isinstance(p, PassoReplay) for p in vistos)


def test_a_velocidade_e_respeitada_entre_candles():
    dormidas: list[float] = []
    r = MarketReplay(serie_alta(n=10),
                     ReplayConfig(symbol="PETR4", velocidade=Velocidade.X10,
                                  minimo_para_analisar=99),
                     relogio=Relogio(Velocidade.X10, dormir=dormidas.append))
    r.executar()

    assert len(dormidas) == 9  # nao espera depois do ultimo
    assert all(d == pytest.approx(6.0) for d in dormidas)


def test_velocidade_maxima_nao_espera():
    dormidas: list[float] = []
    r = MarketReplay(serie_alta(n=10),
                     ReplayConfig(symbol="PETR4", velocidade=Velocidade.MAXIMA,
                                  minimo_para_analisar=99),
                     relogio=Relogio(Velocidade.MAXIMA, dormir=dormidas.append))
    r.executar()

    assert dormidas == []


# --- o pipeline roda a cada candle ------------------------------------------------------


def test_o_pipeline_so_comeca_depois_do_minimo_de_candles():
    r = replay(serie_alta(n=60), minimo_para_analisar=40)
    passos = list(r)

    assert all(p.resultado is None for p in passos[:39])
    assert any(p.resultado is not None for p in passos[39:])


def test_o_pipeline_percorre_as_cinco_etapas():
    r, _ = pregao()
    for passo in r:
        if passo.resultado is not None:
            assert [e.nome for e in passo.resultado.etapas] == [
                "Strategy", "Opportunity", "Score", "Auditor", "Risk Manager"
            ]
            return
    pytest.fail("nenhum passo rodou o pipeline")


def test_uma_operacao_completa_gera_a_sequencia_de_eventos():
    r, _ = pregao()
    r.executar()
    tipos = [e.tipo for e in r.estado.eventos]

    if r.estado.entradas:
        assert TipoEvento.SINAL in tipos
        assert TipoEvento.ENTRADA in tipos
        assert TipoEvento.STOP in tipos
        assert TipoEvento.ALVO in tipos


def test_a_operacao_encerrada_entra_no_diario():
    r, _ = pregao()
    r.executar()

    if r.estado.saidas:
        assert len(r.diario) >= 1
        registro = r.diario.registros[0]
        assert registro.symbol == "PETR4"
        assert registro.setup


def test_nao_abre_posicao_nova_com_posicao_aberta():
    r, _ = pregao()
    for passo in r:
        posicoes = r.broker.get_positions()
        if len(posicoes) > 1:
            pytest.fail("o replay abriu mais de uma posicao no mesmo ativo")


def test_o_estado_serializa():
    r, _ = pregao()
    r.executar(ate=200)
    dados = r.estado.para_dict()
    texto = json.dumps(dados)

    assert dados["symbol"] == "PETR4"
    assert dados["velocidade"] == "maxima"
    assert "eventos" in dados
    assert '"progresso"' in texto


def test_o_resumo_cabe_em_uma_linha():
    r, _ = pregao()
    r.executar(ate=100)
    linha = r.resumo()

    assert "\n" not in linha
    assert "PETR4" in linha


def test_o_replay_e_reproduzivel():
    """Mesma serie, mesma configuracao, mesmos eventos."""
    a, _ = pregao()
    b, _ = pregao()
    a.executar()
    b.executar()

    assert [e.para_dict() for e in a.estado.eventos] == [
        e.para_dict() for e in b.estado.eventos
    ]
