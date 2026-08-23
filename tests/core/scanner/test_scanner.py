"""A varredura: filtros, fluxo de oito etapas, ranking e o caso sem oportunidade."""

from __future__ import annotations

import json

import pytest

from cashinho.core.auditor.checagens import ConfigAuditor
from cashinho.core.auditor import ContrarianAuditor
from cashinho.core.oportunidade import OpportunityEngine
from cashinho.core.risk import RiskConfig, RiskManager, RiskState
from cashinho.core.scanner import (
    ScannerB3,
    ScannerConfig,
    StatusAtivo,
    WATCHLIST_PADRAO,
)
from cashinho.core.scanner.config import ConfiguracaoInvalidaError
from cashinho.data.synthetic import SyntheticProvider

from .factories import (
    ProviderDeTeste,
    risco_folgado,
    scanner,
    serie_curta,
    serie_liquida,
    serie_parada,
    serie_sem_liquidez,
)


# --- watchlist configuravel ------------------------------------------------------


def test_a_watchlist_padrao_tem_acoes_liquidas_da_b3():
    assert "PETR4" in WATCHLIST_PADRAO
    assert len(WATCHLIST_PADRAO) >= 5


def test_a_watchlist_e_configuravel():
    cfg = ScannerConfig(watchlist=("mglu3", " petr4 ", "PETR4"))

    assert cfg.watchlist == ("MGLU3", "PETR4")  # normaliza e remove repetidos


def test_watchlist_vazia_e_recusada():
    with pytest.raises(ConfiguracaoInvalidaError):
        ScannerConfig(watchlist=())


def test_ordenacao_invalida_e_recusada():
    with pytest.raises(ConfiguracaoInvalidaError):
        ScannerConfig(ordenar_por="sorte")


def test_todos_os_ativos_da_watchlist_sao_consultados():
    provider = ProviderDeTeste({"PETR4": serie_liquida("PETR4"), "VALE3": serie_liquida("VALE3")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("PETR4", "VALE3"), dias=3,
                                                atr_min_pct=0.05, liquidez_minima_diaria=1_000.0))
    resultado = sc.varrer()

    assert provider.pedidos == ["PETR4", "VALE3"]
    assert [l.symbol for l in resultado.linhas] == ["PETR4", "VALE3"]


# --- filtros cortam antes do pipeline ---------------------------------------------------


def test_ativo_sem_liquidez_e_cortado_antes_de_analisar():
    provider = ProviderDeTeste({"YYYY3": serie_sem_liquidez("YYYY3")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("YYYY3",), dias=3,
                                                liquidez_minima_diaria=1_000_000.0))
    linha = sc.varrer().linhas[0]

    assert linha.status is StatusAtivo.FILTRADO
    assert "liquidez" in linha.motivo
    # as etapas seguintes nao rodaram
    assert all(not e.executada for e in linha.etapas if e.ordem > 2)


def test_ativo_parado_e_cortado_pela_volatilidade():
    provider = ProviderDeTeste({"XXXX3": serie_parada("XXXX3")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("XXXX3",), dias=3,
                                                liquidez_minima_diaria=1_000.0))
    linha = sc.varrer().linhas[0]

    assert linha.status is StatusAtivo.FILTRADO
    assert "volatilidade" in linha.motivo


def test_ativo_sem_dados_nao_quebra_a_varredura():
    provider = ProviderDeTeste({"PETR4": serie_liquida("PETR4")}, falham=["VALE3"])
    sc = scanner(provider, config=ScannerConfig(watchlist=("PETR4", "VALE3"), dias=3,
                                                atr_min_pct=0.05, liquidez_minima_diaria=1_000.0))
    resultado = sc.varrer()

    por_ativo = {l.symbol: l for l in resultado.linhas}
    assert por_ativo["VALE3"].status is StatusAtivo.SEM_DADOS
    assert por_ativo["PETR4"].status.analisado


def test_spread_informado_corta_o_ativo():
    provider = ProviderDeTeste({"PETR4": serie_liquida("PETR4")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("PETR4",), dias=3,
                                                atr_min_pct=0.05, liquidez_minima_diaria=1_000.0,
                                                spread_maximo_ticks=2.0))
    linha = sc.varrer(spreads={"PETR4": 9.0}).linhas[0]

    assert linha.status is StatusAtivo.FILTRADO
    assert "spread" in linha.motivo


# --- o fluxo de oito etapas --------------------------------------------------------------


def test_cada_ativo_carrega_as_oito_etapas():
    resultado = scanner().varrer()
    esperado = ["Market Data", "Context", "Multi-Timeframe", "Strategy",
                "Opportunity", "Score", "Auditor", "Risk Manager"]

    for linha in resultado.linhas:
        assert [e.nome for e in linha.etapas] == esperado
        assert [e.ordem for e in linha.etapas] == list(range(1, 9))


def test_o_status_diz_onde_o_ativo_parou():
    resultado = scanner().varrer()

    for linha in resultado.analisados:
        parada = next((e for e in linha.etapas if e.executada and not e.passou), None)
        if linha.status is StatusAtivo.LIBERADO:
            assert parada is None
        elif linha.status is StatusAtivo.BARRADO_AUDITOR:
            assert parada.nome == "Auditor"
        elif linha.status is StatusAtivo.BARRADO_RISCO:
            assert parada.nome == "Risk Manager"


def test_o_risco_e_um_so_para_a_varredura_inteira():
    """Perda diaria e exposicao sao limites de carteira, nao de ativo."""
    risco = risco_folgado()
    sc = scanner(risco=risco)

    assert sc.pipeline.risco is risco
    assert sc.risco is risco


def test_auditor_intransigente_barra_no_scanner():
    duro = ContrarianAuditor(score_minimo_pos_auditoria=101.0)
    sc = scanner()
    sc.auditor = duro
    sc.pipeline.auditor = duro
    resultado = sc.varrer()

    assert not resultado.tem_oportunidades
    for linha in resultado.analisados:
        assert linha.status is not StatusAtivo.LIBERADO


# --- isolamento entre ativos ----------------------------------------------------------------


def test_um_ativo_nao_contamina_a_leitura_do_outro():
    """Series diferentes com o mesmo timestamp e tamanho: as caches nao podem trocar."""
    prov = SyntheticProvider(semente=4)
    petr, vale = prov.candles("PETR4", "1m", 3), prov.candles("VALE3", "1m", 3)
    assert petr.last.ts == vale.last.ts and len(petr) == len(vale)

    compartilhado = OpportunityEngine()
    op_petr = compartilhado.avaliar(compartilhado.alimentar(petr).agora(), "PETR4")
    op_vale = compartilhado.avaliar(compartilhado.alimentar(vale).agora(), "VALE3")

    isolado = OpportunityEngine()
    op_vale_sozinho = isolado.avaliar(isolado.alimentar(vale).agora(), "VALE3")

    assert op_vale.score == op_vale_sozinho.score
    assert op_petr.entry != op_vale.entry


def test_a_varredura_da_o_mesmo_resultado_ativo_a_ativo():
    provider = ProviderDeTeste({"PETR4": serie_liquida("PETR4", passo=0.0006),
                                "VALE3": serie_liquida("VALE3", passo=0.0002)})
    cfg = ScannerConfig(watchlist=("PETR4", "VALE3"), dias=3, atr_min_pct=0.01,
                        liquidez_minima_diaria=1_000.0)

    juntos = ScannerB3(provider, cfg, risco=risco_folgado()).varrer()
    sozinhos = {
        a: ScannerB3(provider, cfg.com_watchlist([a]), risco=risco_folgado()).varrer().linhas[0]
        for a in ("PETR4", "VALE3")
    }

    for linha in juntos.linhas:
        assert linha.score == sozinhos[linha.symbol].score
        assert linha.status is sozinhos[linha.symbol].status


# --- ranking -----------------------------------------------------------------------------------


def test_ranking_ordena_por_score_do_maior_para_o_menor():
    resultado = scanner().varrer()
    scores = [l.score for l in resultado.ranking("score")]

    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("criterio", ["score", "rr", "risco", "ativo", "status"])
def test_todas_as_ordenacoes_funcionam(criterio):
    resultado = scanner().varrer()
    linhas = resultado.ranking(criterio)

    assert len(linhas) == len(resultado.linhas)


def test_ordenar_por_ativo_e_alfabetico():
    resultado = scanner().varrer()
    nomes = [l.symbol for l in resultado.ranking("ativo")]

    assert nomes == sorted(nomes)


def test_ranking_pode_limitar_a_quantidade():
    resultado = scanner().varrer()

    assert len(resultado.ranking(limite=2)) == 2


def test_ranking_pode_mostrar_so_o_que_e_operavel():
    resultado = scanner().varrer()
    operaveis = resultado.ranking(apenas_operaveis=True)

    for l in operaveis:
        assert l.status.operavel


# --- nenhuma oportunidade nao e' erro ---------------------------------------------------------------


def test_nenhuma_oportunidade_e_um_resultado_valido():
    provider = ProviderDeTeste({"XXXX3": serie_parada("XXXX3")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("XXXX3",), dias=3,
                                                liquidez_minima_diaria=1_000.0))
    resultado = sc.varrer()

    assert resultado.tem_oportunidades is False
    assert resultado.oportunidades == []
    assert "nenhuma oportunidade" in resultado.resumo
    assert len(resultado.linhas) == 1  # o ativo aparece, com o motivo


def test_watchlist_inteira_cortada_gera_aviso_e_nao_excecao():
    provider = ProviderDeTeste({"A": serie_parada("A"), "B": serie_curta("B")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("A", "B"), dias=3,
                                                liquidez_minima_diaria=1_000.0))
    resultado = sc.varrer()

    assert resultado.analisados == []
    assert any("filtros iniciais" in a for a in resultado.avisos)


def test_resultado_serializa_inteiro():
    dados = scanner().varrer().para_dict()
    texto = json.dumps(dados)

    assert "tem_oportunidades" in dados
    assert dados["ordenado_por"] == "score"
    assert all(set(l) >= {"ativo", "score", "setup", "direcao", "status",
                          "timeframe", "rr", "timestamp"} for l in dados["linhas"])
    assert '"etapas"' in texto
