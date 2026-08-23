"""O diario (filtro e persistencia) e a pagina."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.diario import (
    AMOSTRA_MINIMA,
    DiarioDeTrades,
    Filtro,
    detalhe_registro,
    pagina,
    painel_total,
    resumo,
    tabela_estatisticas,
    tabela_registros,
)
from cashinho.models import Direction

from .factories import BASE, diario, registro

DIARIO = diario()


# --- filtro ---------------------------------------------------------------------


def test_sem_filtro_devolve_tudo_em_ordem():
    registros = DIARIO.filtrar()

    assert len(registros) == 5
    assert [r.aberta_em for r in registros] == sorted(r.aberta_em for r in registros)


def test_filtra_por_ativo():
    assert len(DIARIO.filtrar(Filtro(ativo="PETR4"))) == 3


def test_filtra_por_setup():
    assert len(DIARIO.filtrar(Filtro(setup="rompimento"))) == 2


def test_filtra_por_periodo():
    dia = BASE.date()
    assert len(DIARIO.filtrar(Filtro(inicio=dia, fim=dia))) == 2


def test_filtra_por_resultado():
    assert len(DIARIO.filtrar(Filtro(resultado="perdedor"))) == 2
    assert len(DIARIO.filtrar(Filtro(resultado="vencedor"))) == 3


def test_filtra_por_timeframe():
    assert len(DIARIO.filtrar(Filtro(timeframe="15m"))) == 5  # 15m aparece na tendencia
    assert len(DIARIO.filtrar(Filtro(timeframe="30m"))) == 0


def test_lista_ativos_setups_e_periodo():
    assert DIARIO.ativos() == ["ITUB4", "PETR4", "VALE3"]
    assert len(DIARIO.setups()) == 2
    inicio, fim = DIARIO.periodo()
    assert inicio <= fim


def test_estatistica_respeita_o_filtro():
    todos = DIARIO.estatistica()
    so_petr = DIARIO.estatistica(Filtro(ativo="PETR4"))

    assert todos.n_trades == 5
    assert so_petr.n_trades == 3


# --- persistencia ------------------------------------------------------------------


def test_salva_e_carrega_em_jsonl(tmp_path):
    arquivo = DIARIO.salvar(tmp_path / "diario.jsonl")
    voltou = DiarioDeTrades.carregar(arquivo)

    assert len(voltou) == len(DIARIO)
    assert [r.symbol for r in voltou] == [r.symbol for r in DIARIO]
    assert len(arquivo.read_text().strip().splitlines()) == 5


def test_anexar_acrescenta_sem_reescrever(tmp_path):
    arquivo = tmp_path / "diario.jsonl"
    d = DiarioDeTrades()
    d.anexar(arquivo, registro(100.0))
    d.anexar(arquivo, registro(-50.0))

    assert len(DiarioDeTrades.carregar(arquivo)) == 2


def test_arquivo_inexistente_vira_diario_vazio(tmp_path):
    assert len(DiarioDeTrades.carregar(tmp_path / "nao-existe.jsonl")) == 0


def test_linha_corrompida_nao_derruba_o_diario(tmp_path):
    arquivo = tmp_path / "diario.jsonl"
    DIARIO.salvar(arquivo)
    with arquivo.open("a") as fh:
        fh.write("{isso nao e json}\n")

    assert len(DiarioDeTrades.carregar(arquivo)) == 5


def test_serializa_com_agrupamentos():
    dados = DIARIO.para_dict()
    texto = json.dumps(dados)

    assert dados["total_de_registros"] == 5
    assert set(dados["agrupamentos"]) == {"setup", "ativo", "horario", "dia", "timeframe"}
    assert '"registros"' in texto


# --- pagina ---------------------------------------------------------------------------


def test_a_pagina_tem_resumo_operacoes_e_agrupamentos():
    texto = pagina(DIARIO)

    assert "DIARIO DE TRADES" in texto
    assert "RESUMO" in texto
    assert "OPERACOES" in texto
    for titulo in ("POR SETUP", "POR ATIVO", "POR HORARIO", "POR DIA DA SEMANA", "POR TIMEFRAME"):
        assert titulo in texto


def test_a_pagina_mostra_o_filtro_aplicado():
    texto = pagina(DIARIO, Filtro(ativo="PETR4", resultado="vencedor"))

    assert "PETR4" in texto
    assert "vencedor" in texto
    assert "de 5 operacoes" in texto


def test_a_pagina_avisa_quando_o_recorte_fica_vazio():
    texto = pagina(DIARIO, Filtro(ativo="MGLU3"))

    assert "nenhuma operacao neste recorte" in texto
    assert "5 operacao(oes) em outros recortes" in texto


def test_a_pagina_avisa_amostra_pequena():
    texto = pagina(DIARIO)

    assert "pouco confiavel" in texto or "dizem pouco" in texto


def test_a_pagina_deixa_claro_que_nao_decide():
    texto = pagina(DIARIO)

    assert "mede, nao decide" in texto
    assert "sem nenhum ajuste automatico" in texto


def test_os_agrupamentos_podem_ser_escolhidos():
    texto = pagina(DIARIO, agrupamentos=["setup"])

    assert "POR SETUP" in texto
    assert "POR ATIVO" not in texto


def test_a_lista_de_operacoes_pode_ser_limitada():
    texto = tabela_registros(DIARIO.filtrar(), limite=2)

    assert "e mais 3 operacao(oes)" in texto


def test_o_detalhe_mostra_os_dois_porques():
    r = DIARIO.filtrar(Filtro(resultado="perdedor"))[0]
    texto = detalhe_registro(r)

    assert "MOTIVO DA ENTRADA" in texto
    assert "MOTIVO DA SAIDA" in texto
    assert "CONDICOES DO MERCADO NA ENTRADA" in texto
    assert "AVISOS DO AUDITOR" in texto


def test_o_detalhe_de_um_ganho_nao_inventa_avisos():
    r = DIARIO.filtrar(Filtro(resultado="vencedor"))[0]

    assert "AVISOS DO AUDITOR" not in detalhe_registro(r)


def test_valores_indefinidos_aparecem_como_traco():
    """Sem perdas, payoff e profit factor nao existem."""
    so_ganhos = DiarioDeTrades([registro(100.0), registro(200.0)])
    texto = painel_total(so_ganhos.estatistica())

    assert "payoff -" in texto


def test_cores_sao_opcionais():
    assert "\033[" not in pagina(DIARIO, cores=False)
    assert "\033[" in pagina(DIARIO, cores=True)


def test_resumo_cabe_em_uma_linha():
    linha = resumo(DIARIO)

    assert "\n" not in linha
    assert "operacoes" in linha and "win" in linha
