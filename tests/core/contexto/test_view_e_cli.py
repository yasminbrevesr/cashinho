"""A secao CONTEXTO DO MERCADO e a linha de comando."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from cashinho.core.contexto import (
    DOLAR,
    IBOVESPA,
    MINERIO,
    Correlacao,
    DirecaoDeMercado,
    EstadoDaLeitura,
    Leitura,
    MarketContext,
    MotorDeContexto,
    NivelDeQualidade,
    NivelDeVolatilidade,
    QualidadeDeDados,
    RegimeDeMercado,
    linha_do_instrumento,
    pagina,
    secao_contexto,
    secao_correlacoes,
)
from cashinho.core.contexto.__main__ import main
from cashinho.models import BRT

from .factories import FonteFalsa, config, serie_de_dias

AGORA = datetime(2026, 8, 21, 12, 30, tzinfo=BRT)


@pytest.fixture
def contexto():
    return MarketContext(
        timestamp=AGORA,
        market_regime=RegimeDeMercado.RISCO_LIGADO,
        ibovespa_direction=DirecaoDeMercado.ALTA,
        volatility=NivelDeVolatilidade.NORMAL,
        relevant_correlations=(Correlacao("Ibovespa", "Dolar (USD/BRL)", -0.68, 120, "60m"),),
        data_quality=QualidadeDeDados(NivelDeQualidade.PARCIAL, 4, 6,
                                      faltantes=("Nasdaq Composite",),
                                      sem_fonte=("Minerio de ferro",),
                                      defasagem_minutos=15),
        leituras=(
            Leitura(IBOVESPA, EstadoDaLeitura.OK, 134210.0, 0.84, AGORA, 15, "yahoo"),
            Leitura(DOLAR, EstadoDaLeitura.OK, 5.4210, -0.31, AGORA, 15, "yahoo"),
            Leitura(MINERIO, EstadoDaLeitura.SEM_FONTE, detalhe="FONTE A CONFIRMAR"),
        ),
        notas=("Ibovespa em alta (+0.84%)",),
        criterio_correlacao="|r| >= 0,40 com ao menos 30 pontos",
    )


# --- a secao pedida ------------------------------------------------------------


def test_a_secao_tem_o_titulo_pedido(contexto):
    assert "CONTEXTO DO MERCADO" in secao_contexto(contexto)


def test_a_secao_mostra_os_campos_do_contrato(contexto):
    texto = secao_contexto(contexto)

    assert "RISCO LIGADO" in texto      # market_regime
    assert "IBOVESPA" in texto          # ibovespa_direction
    assert "ALTA" in texto
    assert "VOLATILIDADE" in texto      # volatility
    assert "NORMAL" in texto
    assert "QUALIDADE" in texto         # data_quality
    assert "CORRELACOES" in texto       # relevant_correlations
    assert "21/08 12:30" in texto       # timestamp


def test_todo_instrumento_aparece_mesmo_sem_numero(contexto):
    """Esconder a linha faria o contexto parecer mais completo do que e'."""
    texto = secao_contexto(contexto)

    assert "Minerio de ferro" in texto
    assert "FONTE A CONFIRMAR" in texto


def test_a_linha_sem_numero_nao_mostra_zero():
    linha = linha_do_instrumento(Leitura(MINERIO, EstadoDaLeitura.SEM_FONTE))

    assert "0,00" not in linha and "0.00" not in linha
    assert "-" in linha


def test_a_tela_diz_que_o_contexto_nao_gera_operacao(contexto):
    assert "NAO gera operacao" in secao_contexto(contexto)


def test_a_qualidade_aparece_com_o_resumo(contexto):
    texto = secao_contexto(contexto)

    assert "PARCIAL" in texto
    assert "4 de 6 fontes" in texto
    assert "atraso 15 min" in texto


def test_a_correlacao_mostra_a_amostra(contexto):
    texto = secao_contexto(contexto)

    assert "-0.68" in texto
    assert "120 pontos" in texto


def test_sem_correlacao_a_tela_explica_o_criterio(contexto):
    texto = secao_correlacoes((), "|r| >= 0,40 com ao menos 30 pontos")

    assert "nenhum par" in texto
    assert "30 pontos" in texto


def test_sem_contexto_a_secao_diz_isso():
    assert "nao carregado" in secao_contexto(None)


def test_a_pagina_aceita_cores(contexto):
    assert "\x1b[" in pagina(contexto, cores=True)
    assert "\x1b[" not in pagina(contexto, cores=False)


def test_a_secao_entra_na_tela_da_oportunidade(contexto):
    from cashinho.core.oportunidade.view import pagina_oportunidade
    from cashinho.core.oportunidade.modelos import Opportunity

    op = Opportunity(
        symbol="PETR4", timestamp=AGORA, direction=None, setup="teste", score=0.0,
        entry=None, stop=None, target=None, risk_reward=0.0,
        timeframe_context="60m", timeframe_trend="15m", timeframe_setup="5m",
        timeframe_trigger="1m", reasons=(), warnings=(), invalidation="-",
        expires_at=None,
    )

    sem = pagina_oportunidade(op)
    com = pagina_oportunidade(op, contexto=contexto)

    assert "CONTEXTO DO MERCADO" not in sem
    assert "CONTEXTO DO MERCADO" in com


# --- a linha de comando ------------------------------------------------------------


def test_cli_mostra_a_secao(capsys):
    assert main(["--fonte", "demo", "--dias", "10", "--sem-cor"]) == 0
    saida = capsys.readouterr().out

    assert "CONTEXTO DO MERCADO" in saida
    assert "simulados" in saida


def test_cli_em_json(capsys):
    assert main(["--dias", "10", "--json"]) == 0
    dados = json.loads(capsys.readouterr().out)

    assert set(dados) >= {"timestamp", "market_regime", "ibovespa_direction",
                          "volatility", "relevant_correlations", "data_quality"}


def test_cli_lista_os_instrumentos_e_suas_fontes(capsys):
    assert main(["--listar-instrumentos"]) == 0
    saida = capsys.readouterr().out

    assert "Ibovespa" in saida and "yahoo" in saida
    assert "Juros" in saida and "bcb" in saida
    assert "FONTE A CONFIRMAR" in saida


def test_cli_aceita_subconjunto_de_instrumentos(capsys):
    main(["--instrumentos", "ibovespa,dolar", "--dias", "10", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert {l["chave"] for l in dados["leituras"]} == {"ibovespa", "dolar"}


def test_cli_recusa_instrumento_desconhecido():
    with pytest.raises(SystemExit):
        main(["--instrumentos", "bitcoin"])


def test_cli_com_fonte_demo_nunca_diz_qualidade_boa(capsys):
    main(["--dias", "10", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["data_quality"]["nivel"] == "simulada"
    assert dados["data_quality"]["confiavel"] is False
    assert dados["utilizavel"] is False
