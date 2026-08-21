"""Configuracao, persistencia e contabilidade do estado."""

from __future__ import annotations

import json
from datetime import date

import pytest

from cashinho.core.risk import ConfiguracaoInvalidaError, RiskConfig, RiskState
from cashinho.core.risk.models import Position
from cashinho.models import BRT, Direction

from .factories import AGORA, compra, config, gerente, perder


# --- validacao ------------------------------------------------------------------


@pytest.mark.parametrize(
    "campos",
    [
        {"capital": 0},
        {"capital": -100},
        {"risco_por_trade_pct": 0},
        {"risco_por_trade_pct": 101},
        {"perda_max_diaria_pct": 0},
        {"drawdown_max_pct": 0},
        {"exposicao_max_total_pct": 0},
        {"exposicao_max_total_pct": 120},
        {"max_trades_dia": 0},
        {"max_perdas_consecutivas": 0},
        {"lote": 0},
        {"custo_por_trade": -1},
        {"risco_max_monetario": 0},
        {"perda_max_diaria_valor": -5},
        {"exposicao_max_por_ativo_pct": 80, "exposicao_max_total_pct": 50},
    ],
)
def test_configuracao_impossivel_e_recusada(campos):
    with pytest.raises(ConfiguracaoInvalidaError):
        RiskConfig(**campos)


def test_limites_derivados():
    c = RiskConfig(capital=50_000, risco_por_trade_pct=0.5, perda_max_diaria_pct=2.0,
                   exposicao_max_por_ativo_pct=15.0, exposicao_max_total_pct=45.0,
                   drawdown_max_pct=8.0)

    assert c.risco_alvo() == pytest.approx(250.0)
    assert c.perda_max_diaria() == pytest.approx(1_000.0)
    assert c.teto_exposicao_ativo() == pytest.approx(7_500.0)
    assert c.teto_exposicao_total() == pytest.approx(22_500.0)
    assert c.drawdown_max(60_000) == pytest.approx(4_800.0)


def test_tetos_absolutos_vencem_os_percentuais():
    c = RiskConfig(capital=100_000, risco_por_trade_pct=1.0, risco_max_monetario=250.0,
                   perda_max_diaria_pct=3.0, perda_max_diaria_valor=500.0)

    assert c.risco_alvo() == 250.0
    assert c.perda_max_diaria() == 500.0


def test_atualizar_devolve_nova_config_validada():
    c = RiskConfig(capital=10_000)
    nova = c.atualizar(capital=20_000, risco_por_trade_pct=2.0)

    assert nova.capital == 20_000
    assert c.capital == 10_000  # a original nao muda
    with pytest.raises(ConfiguracaoInvalidaError):
        c.atualizar(capital=-1)
    with pytest.raises(ConfiguracaoInvalidaError):
        c.atualizar(campo_que_nao_existe=1)


def test_persistencia_da_config(tmp_path):
    c = RiskConfig(capital=33_000, risco_por_trade_pct=0.75, max_trades_dia=4)
    arquivo = c.salvar(tmp_path / "risco.json")

    assert json.loads(arquivo.read_text())["capital"] == 33_000
    assert RiskConfig.carregar(arquivo) == c
    assert RiskConfig.carregar(tmp_path / "nao-existe.json") == RiskConfig()


def test_config_ignora_campos_desconhecidos_do_arquivo():
    c = RiskConfig.de_dict({"capital": 5_000, "coisa_estranha": True})
    assert c.capital == 5_000


# --- estado --------------------------------------------------------------------------


def test_exposicao_soma_as_posicoes():
    e = RiskState(capital_inicial=100_000)
    e.registrar_abertura(Position("PETR4", Direction.LONG, 100, 30.0, 29.0, AGORA))
    e.registrar_abertura(Position("VALE3", Direction.SHORT, 200, 60.0, 62.0, AGORA))

    assert e.exposicao_total() == pytest.approx(3_000 + 12_000)
    assert e.exposicao_de("petr4") == pytest.approx(3_000)
    assert e.caixa_disponivel() == pytest.approx(85_000)
    assert e.tem_posicao("VALE3") and not e.tem_posicao("ITUB4")


def test_nao_da_para_abrir_duas_posicoes_no_mesmo_ativo():
    e = RiskState(capital_inicial=100_000)
    e.registrar_abertura(Position("PETR4", Direction.LONG, 100, 30.0, 29.0, AGORA))

    with pytest.raises(ValueError, match="ja existe posicao"):
        e.registrar_abertura(Position("PETR4", Direction.LONG, 100, 30.0, 29.0, AGORA))


def test_caixa_nunca_fica_negativo():
    e = RiskState(capital_inicial=1_000)
    e.registrar_abertura(Position("PETR4", Direction.LONG, 1_000, 30.0, 29.0, AGORA))

    assert e.caixa_disponivel() == 0.0


def test_capital_inicial_invalido_e_recusado():
    with pytest.raises(ValueError):
        RiskState(capital_inicial=0)


def test_aporte_de_capital_nao_cria_nem_apaga_drawdown():
    rm = gerente(config(capital=10_000.0, max_trades_dia=50, max_perdas_consecutivas=50,
                        perda_max_diaria_pct=100.0))
    perder(rm, 500.0)
    drawdown_antes = rm.estado.drawdown

    rm.atualizar_config(capital=20_000.0)

    assert rm.estado.drawdown == pytest.approx(drawdown_antes)
    assert rm.estado.patrimonio == pytest.approx(19_500.0)
    assert rm.config.capital == 20_000.0


def test_estado_vai_e_volta_do_disco():
    rm = gerente(config(capital=10_000.0))
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    rm.acionar_kill_switch("teste de persistencia")

    dados = rm.estado.para_dict_completo()
    voltou = RiskState.de_dict(json.loads(json.dumps(dados)))

    assert voltou.patrimonio == rm.estado.patrimonio
    assert voltou.trades_dia == rm.estado.trades_dia
    assert voltou.exposicao_total() == pytest.approx(rm.estado.exposicao_total())
    assert voltou.kill_switch.codigo == "manual"
    assert voltou.posicoes["PETR4"].quantidade == rm.estado.posicoes["PETR4"].quantidade
