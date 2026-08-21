"""O contrato do Signal - o que toda estrategia precisa devolver."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from cashinho.core.strategy import Action, Factor, Signal
from cashinho.models import BRT, Direction

QUANDO = datetime(2026, 8, 20, 12, 35, tzinfo=BRT)


def _sinal(**campos) -> Signal:
    base = dict(
        symbol="PETR4",
        timestamp=QUANDO,
        timeframe="5m",
        action=Action.BUY,
        setup="teste",
        confidence=0.8,
        reasons=("porque sim",),
        invalidation="perder a media",
    )
    base.update(campos)
    return Signal(**base)


def test_os_quatro_estados_existem():
    assert [a.value for a in Action] == ["BUY", "SELL", "WAIT", "NONE"]


def test_apenas_buy_e_sell_sao_acionaveis():
    assert Action.BUY.acionavel and Action.SELL.acionavel
    assert not Action.WAIT.acionavel and not Action.NONE.acionavel


def test_acao_conhece_a_direcao_correspondente():
    assert Action.BUY.direcao is Direction.LONG
    assert Action.SELL.direcao is Direction.SHORT
    assert Action.WAIT.direcao is None
    assert Action.NONE.direcao is None


def test_signal_tem_os_campos_do_contrato():
    s = _sinal()
    for campo in ("symbol", "timestamp", "timeframe", "action", "setup",
                  "confidence", "reasons", "invalidation"):
        assert hasattr(s, campo)


def test_confianca_fora_da_faixa_e_recusada():
    with pytest.raises(ValueError, match="entre 0 e 1"):
        _sinal(confidence=1.4)
    with pytest.raises(ValueError, match="entre 0 e 1"):
        _sinal(confidence=-0.1)


def test_sinal_acionavel_sem_justificativa_e_recusado():
    with pytest.raises(ValueError, match="precisa dizer por que"):
        _sinal(reasons=())


def test_wait_e_none_podem_vir_sem_justificativa():
    assert _sinal(action=Action.WAIT, reasons=()).action is Action.WAIT
    assert _sinal(action=Action.NONE, reasons=()).action is Action.NONE


def test_fatores_se_separam_em_favor_contra_e_neutro():
    fatores = (
        Factor("volume", True, "acima da media"),
        Factor("candle", False, "contra o vies"),
        Factor("doji", None, "sem corpo"),
        Factor("empilhamento", False, "fora de ordem", obrigatorio=True),
    )
    s = _sinal(factors=fatores)

    assert [f.nome for f in s.favoraveis] == ["volume"]
    assert [f.nome for f in s.contrarios] == ["candle", "empilhamento"]
    assert [f.nome for f in s.neutros] == ["doji"]
    assert [f.nome for f in s.faltando] == ["empilhamento"]  # so os obrigatorios


def test_simbolo_do_fator_ajuda_a_tela():
    assert Factor("x", True, "").simbolo == "✔"
    assert Factor("x", False, "").simbolo == "✖"
    assert Factor("x", None, "").simbolo == "·"


def test_signal_serializa_para_a_interface():
    s = _sinal(factors=(Factor("volume", True, "acima da media"),), niveis={"entrada_referencia": 31.0})
    dados = s.para_dict()
    texto = json.dumps(dados)

    assert dados["action"] == "BUY"
    assert dados["factors"][0]["favoravel"] is True
    assert dados["niveis"]["entrada_referencia"] == 31.0
    assert '"symbol": "PETR4"' in texto


def test_signal_nao_carrega_quantidade_nem_ordem():
    """Dimensionar e' com o Risk Manager; executar, com o operador."""
    campos = set(_sinal().para_dict())

    assert not campos & {"quantidade", "position_size", "ordem", "boleta", "enviar"}
