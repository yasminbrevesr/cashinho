"""A tela do Scanner: colunas, ordenacao e o aviso de nada encontrado."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.scanner import (
    LinhaScanner,
    ResultadoScanner,
    ScannerConfig,
    StatusAtivo,
    detalhe,
    faixa_sem_oportunidade,
    linha_da_tabela,
    pagina,
    tabela,
)
from cashinho.core.scanner.filtros import Filtro
from cashinho.models import BRT, Direction

from .factories import (
    ProviderDeTeste,
    scanner,
    serie_liquida,
    serie_parada,
)

AGORA = datetime(2026, 8, 20, 12, 37, tzinfo=BRT)


def _linha(symbol="PETR4", status=StatusAtivo.LIBERADO, score=84.0, **campos) -> LinhaScanner:
    from cashinho.core.oportunidade.estados import EstadoOportunidade
    from cashinho.core.oportunidade.modelos import Opportunity

    op = Opportunity(
        symbol=symbol, timestamp=AGORA, direction=Direction.LONG,
        setup="pullback a favor da tendencia", score=score,
        entry=31.0, stop=30.7, target=31.9, risk_reward=3.0,
        timeframe_context="60m", timeframe_trend="15m",
        timeframe_setup="5m", timeframe_trigger="1m",
        reasons=("teste",), warnings=(), invalidation="-",
        expires_at=AGORA + timedelta(minutes=3),
        estado=EstadoOportunidade.APROVADO,
    )
    campos.setdefault("oportunidade", op)
    return LinhaScanner(symbol=symbol, status=status, timestamp=AGORA, **campos)


def _resultado(linhas, **cfg) -> ResultadoScanner:
    return ResultadoScanner(instante=AGORA, linhas=list(linhas),
                            config=ScannerConfig(watchlist=("PETR4",), **cfg))


# --- as colunas pedidas ---------------------------------------------------------


def test_a_tabela_tem_as_nove_colunas():
    texto = tabela(_resultado([_linha()]))

    for coluna in ("ATIVO", "SCORE", "SETUP", "DIR", "STATUS", "TF", "R:R", "RISCO", "HORA"):
        assert coluna in texto


def test_a_linha_traz_os_dados_do_ativo():
    texto = linha_da_tabela(_linha())

    assert "PETR4" in texto
    assert "84.0" in texto
    assert "pullback" in texto
    assert "COMPRA" in texto
    assert "LIBERADO" in texto
    assert "5m" in texto
    assert "3.00" in texto
    assert "12:37" in texto


def test_setup_longo_e_truncado_sem_quebrar_a_coluna():
    linha = _linha()
    object.__setattr__(linha.oportunidade, "setup", "um setup com nome absurdamente longo " * 3)
    texto = linha_da_tabela(linha)

    assert "…" in texto
    assert len(texto.splitlines()) == 1


def test_ativo_sem_oportunidade_mostra_tracos():
    texto = linha_da_tabela(
        LinhaScanner("XXXX3", StatusAtivo.FILTRADO, "sem liquidez", timestamp=AGORA)
    )

    assert "XXXX3" in texto
    assert "FILTRADO" in texto
    assert "-" in texto


# --- ordenacao --------------------------------------------------------------------


def test_a_tabela_ordena_por_score_por_padrao():
    r = _resultado([_linha("AAAA3", score=40.0), _linha("BBBB3", score=90.0)])
    texto = tabela(r)

    assert texto.index("BBBB3") < texto.index("AAAA3")


def test_a_ordenacao_pode_ser_trocada_na_chamada():
    r = _resultado([_linha("ZZZZ3", score=90.0), _linha("AAAA3", score=40.0)])
    por_ativo = tabela(r, ordenar_por="ativo")

    assert por_ativo.index("AAAA3") < por_ativo.index("ZZZZ3")


def test_o_limite_corta_a_tabela():
    r = _resultado([_linha(f"AT{i}3", score=float(i)) for i in range(5)])
    texto = tabela(r, limite=2)

    de_ativo = [l for l in texto.splitlines() if l.startswith("  AT") and "ATIVO" not in l]
    assert len(de_ativo) == 2


# --- nenhuma oportunidade ----------------------------------------------------------


def test_a_faixa_de_nada_encontrado_e_destacada():
    texto = faixa_sem_oportunidade()

    assert "NENHUMA OPORTUNIDADE ENCONTRADA" in texto
    assert "╔" in texto


def test_a_pagina_mostra_a_faixa_quando_nada_foi_liberado():
    r = _resultado([_linha(status=StatusAtivo.REJEITADO)])
    texto = pagina(r)

    assert "NENHUMA OPORTUNIDADE ENCONTRADA" in texto
    assert "resultado esperado na maior parte do pregao" in texto


def test_a_pagina_nao_mostra_a_faixa_quando_ha_oportunidade():
    texto = pagina(_resultado([_linha()]))

    assert "NENHUMA OPORTUNIDADE ENCONTRADA" not in texto
    assert "1 oportunidade(s) liberada(s): PETR4" in texto


def test_ativos_cortados_aparecem_com_o_motivo():
    r = _resultado([
        _linha(),
        LinhaScanner("XXXX3", StatusAtivo.FILTRADO, "volatilidade: ATR de 0.03%"),
    ])
    texto = pagina(r)

    assert "CORTADOS NOS FILTROS" in texto
    assert "ATR de 0.03%" in texto


def test_cores_sao_opcionais():
    r = _resultado([_linha()])

    assert "\033[" not in pagina(r, cores=False)
    assert "\033[" in pagina(r, cores=True)


# --- detalhe de um ativo ------------------------------------------------------------------


def test_o_detalhe_mostra_filtros_e_as_oito_etapas():
    provider = ProviderDeTeste({"PETR4": serie_liquida("PETR4")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("PETR4",), dias=3,
                                                atr_min_pct=0.01, liquidez_minima_diaria=1_000.0))
    linha = sc.varrer().linhas[0]
    texto = detalhe(linha)

    assert "FILTROS INICIAIS" in texto
    assert "liquidez" in texto
    assert "FLUXO" in texto
    for etapa in ("Market Data", "Context", "Multi-Timeframe", "Strategy",
                  "Opportunity", "Score", "Auditor", "Risk Manager"):
        assert etapa in texto


def test_o_detalhe_de_um_ativo_cortado_mostra_as_etapas_nao_executadas():
    provider = ProviderDeTeste({"XXXX3": serie_parada("XXXX3")})
    sc = scanner(provider, config=ScannerConfig(watchlist=("XXXX3",), dias=3,
                                                liquidez_minima_diaria=1_000.0))
    texto = detalhe(sc.varrer().linhas[0])

    assert "nao executada" in texto
    assert "volatilidade" in texto
