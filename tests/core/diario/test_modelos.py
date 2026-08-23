"""O registro e o filtro."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from cashinho.core.diario import DIAS_DA_SEMANA, Filtro, Registro
from cashinho.models import Direction

from .factories import BASE, registro


def test_o_registro_tem_todos_os_campos_pedidos():
    dados = registro().para_dict()

    for campo in ("data", "horario", "symbol", "direcao", "setup", "score",
                  "timeframe_context", "timeframe_trend", "timeframe_setup",
                  "timeframe_trigger", "entrada", "stop", "alvo", "quantidade",
                  "saida", "resultado", "risco", "rr", "motivo_entrada",
                  "motivo_saida", "condicoes_de_mercado", "warnings_auditor"):
        assert campo in dados


def test_risco_e_quantidade_vezes_distancia_ate_o_stop():
    r = registro(quantidade=300, stop_distancia=0.30)

    assert r.risco_por_acao == pytest.approx(0.30)
    assert r.risco == pytest.approx(90.0)


def test_rr_usa_o_alvo_planejado():
    r = registro(stop_distancia=0.30)  # alvo a 0,60

    assert r.rr == pytest.approx(2.0)


def test_resultado_em_r_compara_ativos_diferentes():
    caro = registro(resultado=180.0, quantidade=300, stop_distancia=0.30)  # risco 90
    barato = registro(resultado=60.0, quantidade=100, stop_distancia=0.30)  # risco 30

    assert caro.resultado_em_r == pytest.approx(2.0)
    assert barato.resultado_em_r == pytest.approx(2.0)


def test_sem_stop_o_risco_e_zero_e_nao_quebra():
    r = registro(stop_distancia=0.0)

    assert r.risco == 0.0
    assert r.rr == 0.0
    assert r.resultado_em_r == 0.0


def test_hora_e_dia_vem_da_entrada():
    r = registro(quando=BASE)  # segunda, 10:30

    assert r.hora == 10
    assert r.dia_da_semana == "segunda"
    assert r.dia_da_semana in DIAS_DA_SEMANA


def test_duracao_e_calculada():
    assert registro(duracao_min=42).duracao_minutos == pytest.approx(42.0)


def test_resultado_bruto_desconta_os_custos():
    r = registro(resultado=200.0, custos=15.0)

    assert r.resultado_bruto == pytest.approx(215.0)
    assert r.venceu and not r.perdeu


def test_registro_vai_e_volta_de_json():
    original = registro(-90.0)
    voltou = Registro.de_dict(json.loads(json.dumps(original.para_dict())))

    assert voltou.symbol == original.symbol
    assert voltou.resultado == original.resultado
    assert voltou.motivo_entrada == original.motivo_entrada
    assert voltou.warnings_auditor == original.warnings_auditor
    assert voltou.id == original.id


# --- filtros --------------------------------------------------------------------


def test_filtro_vazio_aceita_tudo():
    assert Filtro().aceita(registro()) is True
    assert Filtro().vazio is True


def test_filtro_por_ativo_ignora_maiusculas():
    r = registro(symbol="PETR4")

    assert Filtro(ativo="petr4").aceita(r) is True
    assert Filtro(ativo="VALE3").aceita(r) is False


def test_filtro_por_setup_aceita_trecho():
    r = registro(setup="pullback a favor da tendencia")

    assert Filtro(setup="pullback").aceita(r) is True
    assert Filtro(setup="rompimento").aceita(r) is False


def test_filtro_por_timeframe():
    r = registro(timeframe_setup="5m")

    assert Filtro(timeframe="5m").aceita(r) is True
    assert Filtro(timeframe="30m").aceita(r) is False


def test_filtro_por_periodo():
    r = registro(quando=BASE)
    dia = BASE.date()

    assert Filtro(inicio=dia).aceita(r) is True
    assert Filtro(fim=dia).aceita(r) is True
    assert Filtro(inicio=dia + timedelta(days=1)).aceita(r) is False
    assert Filtro(fim=dia - timedelta(days=1)).aceita(r) is False


def test_filtro_por_resultado():
    ganho = registro(200.0)
    perda = registro(-90.0)

    assert Filtro(resultado="vencedor").aceita(ganho) is True
    assert Filtro(resultado="vencedor").aceita(perda) is False
    assert Filtro(resultado="perdedor").aceita(perda) is True


def test_filtro_por_direcao():
    r = registro(direcao=Direction.LONG)

    assert Filtro(direcao=Direction.LONG).aceita(r) is True
    assert Filtro(direcao=Direction.SHORT).aceita(r) is False


def test_filtros_se_combinam():
    r = registro(200.0, symbol="PETR4", setup="pullback a favor")
    combinado = Filtro(ativo="PETR4", setup="pullback", resultado="vencedor")

    assert combinado.aceita(r) is True
    assert Filtro(ativo="PETR4", resultado="perdedor").aceita(r) is False


def test_a_descricao_do_filtro_lista_o_recorte():
    texto = Filtro(ativo="petr4", setup="pullback", resultado="vencedor").descricao()

    assert "PETR4" in texto
    assert "pullback" in texto
    assert "vencedor" in texto
    assert Filtro().descricao() == "sem filtro"
