"""A pagina Paper Trading e o CLI."""

from __future__ import annotations

import json

import pytest

from cashinho.core.broker import (
    Order,
    OrderStatus,
    OrderType,
    faixa_kill_switch,
    pagina,
    painel_saldo,
    tabela_operacoes,
    tabela_ordens,
    tabela_posicoes,
)
from cashinho.core.broker.view import resumo
from cashinho.models import Direction

from .factories import com_risco, ordem, paper


def _com_movimento():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100, stop_referencia=30.70))
    b.broker.atualizar_preco("PETR4", 31.50)
    b.place_order(ordem(OrderType.MARKET, side=Direction.SHORT, quantidade=40))
    b.place_order(ordem(OrderType.LIMIT, quantidade=50, preco_limite=30.0,
                        stop_referencia=29.5))
    return b


# --- os blocos pedidos -----------------------------------------------------------


def test_a_pagina_tem_os_sete_blocos():
    texto = pagina(_com_movimento())

    assert "PAPER TRADING" in texto
    assert "saldo em caixa" in texto
    assert "patrimonio" in texto
    assert "POSICOES" in texto
    assert "ORDENS ABERTAS" in texto
    assert "OPERACOES" in texto
    assert "P&L do dia" in texto
    assert "P&L acumulado" in texto


def test_o_painel_de_conta_mostra_os_numeros():
    b = _com_movimento()
    texto = painel_saldo(b.get_balance(), b.broker.pnl_aberto())

    assert "exposicao" in texto
    assert "retorno" in texto
    assert "custos" in texto


def test_a_tabela_de_posicoes_marca_a_mercado():
    b = _com_movimento()
    texto = tabela_posicoes(b.get_positions(), b.broker._precos)

    assert "PETR4" in texto
    assert "P&L ABERTO" in texto
    assert "31.50" in texto


def test_sem_posicao_a_tabela_diz_isso():
    assert "nenhuma posicao aberta" in tabela_posicoes([])


def test_a_tabela_de_ordens_mostra_status_e_motivo():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))  # sem stop: rejeitada
    texto = tabela_ordens(b.get_orders(), "ORDENS")

    assert "rejeitada" in texto
    assert "sem stop de referencia" in texto


def test_a_tabela_de_operacoes_mostra_o_resultado():
    b = _com_movimento()
    texto = tabela_operacoes(b.get_trades())

    assert "PETR4" in texto
    assert "RESULTADO" in texto


def test_ordens_barradas_aparecem_em_bloco_proprio():
    b = com_risco()
    b.place_order(ordem(OrderType.MARKET, quantidade=100))
    texto = pagina(b)

    assert "ORDENS BARRADAS" in texto


# --- kill switch ------------------------------------------------------------------


def test_a_faixa_de_kill_switch_e_destacada():
    texto = faixa_kill_switch("fim do expediente")

    assert "KILL SWITCH ACIONADO" in texto
    assert "NOVAS OPERACOES BLOQUEADAS" in texto
    assert "fim do expediente" in texto
    assert "impede abrir, nao sair" in texto


def test_a_pagina_mostra_a_faixa_quando_travada():
    b = _com_movimento()
    b.acionar_kill_switch("fim do expediente")
    texto = pagina(b)

    assert "KILL SWITCH ACIONADO" in texto


def test_a_pagina_normal_nao_mostra_a_faixa():
    assert "KILL SWITCH ACIONADO" not in pagina(_com_movimento())


def test_cores_sao_opcionais():
    b = _com_movimento()

    assert "\033[" not in pagina(b, cores=False)
    assert "\033[" in pagina(b, cores=True)


def test_resumo_cabe_em_uma_linha():
    linha = resumo(_com_movimento())

    assert "\n" not in linha
    assert "patrimonio" in linha
