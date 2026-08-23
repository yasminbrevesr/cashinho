"""O contexto como fator - e o que ele nao consegue fazer.

Este arquivo existe por causa de uma frase do enunciado: *as estrategias podem
utilizar esse contexto como fator adicional, mas ele nao deve gerar operacao
sozinho*. Os testes abaixo tentam, de varias direcoes, fazer o contexto criar
uma operacao.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from cashinho.core.contexto import (
    DOLAR,
    IBOVESPA,
    LIMITE_DE_AJUSTE,
    Correlacao,
    DirecaoDeMercado,
    EstrategiaComContexto,
    MarketContext,
    NivelDeQualidade,
    NivelDeVolatilidade,
    QualidadeDeDados,
    RegimeDeMercado,
    aplicar_contexto,
    fator_de_contexto,
)
from cashinho.core.strategy.models import Action, Factor, Signal
from cashinho.models import BRT, Direction

AGORA = datetime(2026, 8, 21, 11, 0, tzinfo=BRT)


def contexto(regime=RegimeDeMercado.RISCO_LIGADO, nivel=NivelDeQualidade.BOA,
             direcao=DirecaoDeMercado.ALTA,
             volatilidade=NivelDeVolatilidade.NORMAL) -> MarketContext:
    return MarketContext(
        timestamp=AGORA, market_regime=regime, ibovespa_direction=direcao,
        volatility=volatilidade, relevant_correlations=(),
        data_quality=QualidadeDeDados(nivel, 5, 6),
    )


def sinal(action=Action.BUY, confianca=0.6, vies=Direction.LONG) -> Signal:
    return Signal(
        symbol="PETR4", timestamp=AGORA, timeframe="5m", action=action,
        setup="teste", confidence=confianca,
        reasons=("motivo",) if action.acionavel else (),
        invalidation="-", vies=vies,
    )


TODOS_OS_REGIMES = list(RegimeDeMercado)
TODAS_AS_QUALIDADES = list(NivelDeQualidade)


# --- a invariante: o contexto nao cria operacao -------------------------------


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("regime", TODOS_OS_REGIMES)
def test_o_contexto_nunca_muda_a_acao_do_sinal(action, regime):
    original = sinal(action=action)

    resultado = aplicar_contexto(original, contexto(regime=regime))

    assert resultado.action is original.action


@pytest.mark.parametrize("action", [Action.WAIT, Action.NONE])
def test_sinal_que_nao_pede_decisao_nao_ganha_confianca(action):
    """Um WAIT com confianca inflada seria operacao entrando pela porta dos fundos."""
    original = sinal(action=action, confianca=0.5)

    resultado = aplicar_contexto(original, contexto(RegimeDeMercado.RISCO_LIGADO))

    assert resultado.confidence == original.confidence
    assert resultado.action is action


def test_o_melhor_contexto_possivel_nao_torna_um_none_acionavel():
    otimo = contexto(RegimeDeMercado.RISCO_LIGADO, NivelDeQualidade.BOA)

    resultado = aplicar_contexto(sinal(action=Action.NONE, confianca=0.0), otimo)

    assert resultado.action is Action.NONE
    assert resultado.action.acionavel is False
    assert resultado.confidence == 0.0


def test_o_ajuste_e_limitado():
    original = sinal(confianca=0.6)

    resultado = aplicar_contexto(original, contexto())

    assert abs(resultado.confidence - original.confidence) <= LIMITE_DE_AJUSTE + 1e-9


def test_a_confianca_continua_entre_zero_e_um():
    for c in (0.0, 0.97, 1.0):
        r = aplicar_contexto(sinal(confianca=c), contexto())
        assert 0.0 <= r.confidence <= 1.0


def test_o_modulo_de_contexto_nao_constroi_sinal_nem_oportunidade():
    """Nenhum arquivo do contexto pode instanciar um objeto acionavel."""
    import ast
    import pathlib

    proibidos = {"Signal", "Opportunity", "Order", "Ordem"}
    pasta = pathlib.Path("src/cashinho/core/contexto")
    achados = []
    for arquivo in pasta.glob("*.py"):
        if arquivo.name == "fator.py":
            continue  # o fator recebe e devolve Signal: e' a ponte, e nao cria acao
        arvore = ast.parse(arquivo.read_text())
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                if no.func.id in proibidos:
                    achados.append(f"{arquivo.name}:{no.lineno} {no.func.id}")
    assert achados == [], f"contexto criando objeto acionavel: {achados}"


def test_o_fator_so_reusa_a_acao_que_recebeu():
    """Na ponte (fator.py), Signal so aparece via replace de um sinal existente."""
    import pathlib

    texto = pathlib.Path("src/cashinho/core/contexto/fator.py").read_text()

    assert "Action.BUY" not in texto and "Action.SELL" not in texto


# --- o que o fator diz -----------------------------------------------------------


def test_contexto_a_favor_soma_confianca():
    r = aplicar_contexto(sinal(confianca=0.5), contexto(RegimeDeMercado.RISCO_LIGADO))

    assert r.confidence > 0.5
    assert r.factors[-1].favoravel is True


def test_contexto_contra_desconta_confianca():
    r = aplicar_contexto(sinal(confianca=0.5, vies=Direction.LONG),
                         contexto(RegimeDeMercado.RISCO_DESLIGADO,
                                  direcao=DirecaoDeMercado.BAIXA))

    assert r.confidence < 0.5
    assert r.factors[-1].favoravel is False


def test_venda_em_mercado_de_risco_desligado_e_favorecida():
    r = aplicar_contexto(sinal(action=Action.SELL, vies=Direction.SHORT, confianca=0.5),
                         contexto(RegimeDeMercado.RISCO_DESLIGADO,
                                  direcao=DirecaoDeMercado.BAIXA))

    assert r.confidence > 0.5
    assert r.factors[-1].favoravel is True


def test_estresse_e_contra_qualquer_lado():
    for vies, action in ((Direction.LONG, Action.BUY), (Direction.SHORT, Action.SELL)):
        r = aplicar_contexto(
            sinal(action=action, vies=vies, confianca=0.5),
            contexto(RegimeDeMercado.ESTRESSE, volatilidade=NivelDeVolatilidade.EXTREMA))
        assert r.confidence < 0.5
        assert r.factors[-1].favoravel is False


def test_regime_conflitante_nao_pesa_para_lado_nenhum():
    r = aplicar_contexto(sinal(confianca=0.5), contexto(RegimeDeMercado.CONFLITANTE))

    assert r.confidence == 0.5
    assert r.factors[-1].favoravel is None


def test_regime_lateral_nao_pesa():
    r = aplicar_contexto(sinal(confianca=0.5), contexto(RegimeDeMercado.LATERAL))

    assert r.confidence == 0.5


@pytest.mark.parametrize("nivel", [NivelDeQualidade.SIMULADA, NivelDeQualidade.RUIM,
                                   NivelDeQualidade.INDISPONIVEL])
def test_contexto_sem_qualidade_e_lido_mas_nao_pesa(nivel):
    r = aplicar_contexto(sinal(confianca=0.5),
                         contexto(RegimeDeMercado.RISCO_LIGADO, nivel=nivel))

    assert r.confidence == 0.5
    assert r.factors[-1].favoravel is None
    assert nivel.rotulo in r.factors[-1].detalhe


def test_sem_contexto_o_sinal_passa_intacto():
    original = sinal(confianca=0.55)

    r = aplicar_contexto(original, None)

    assert r.confidence == 0.55
    assert r.factors[-1].favoravel is None
    assert "sem contexto" in r.factors[-1].detalhe


def test_sinal_sem_vies_nao_recebe_peso():
    r = aplicar_contexto(sinal(vies=None), contexto(RegimeDeMercado.RISCO_LIGADO))

    assert r.factors[-1].favoravel is None


def test_o_contexto_fica_anexado_ao_sinal():
    ctx = contexto()

    r = aplicar_contexto(sinal(), ctx)

    assert r.extras["contexto"] is ctx


def test_os_fatores_anteriores_sao_preservados():
    original = Signal(
        symbol="PETR4", timestamp=AGORA, timeframe="5m", action=Action.BUY,
        setup="teste", confidence=0.5, reasons=("motivo",), invalidation="-",
        vies=Direction.LONG, factors=(Factor("tendencia", True, "alta"),),
    )

    r = aplicar_contexto(original, contexto())

    assert r.factors[0].nome == "tendencia"
    assert len(r.factors) == 2


def test_o_motivo_do_contexto_entra_nas_justificativas_quando_pesa():
    r = aplicar_contexto(sinal(), contexto(RegimeDeMercado.RISCO_LIGADO))

    assert any("regime" in m.lower() for m in r.reasons)


# --- a estrategia embrulhada ---------------------------------------------------------


class EstrategiaFixa:
    nome = "fixa"
    descricao = "devolve sempre o mesmo sinal"
    timeframe_preferido = "5m"
    experimental = True
    aviso = ""

    def __init__(self, resposta: Signal):
        self.resposta = resposta

    def avaliar(self, contexto):
        return self.resposta


def test_a_estrategia_embrulhada_recebe_o_fator():
    envelope = EstrategiaComContexto(EstrategiaFixa(sinal(confianca=0.5)), contexto())

    r = envelope.avaliar(None)

    assert r.factors[-1].nome == "contexto de mercado"
    assert r.confidence > 0.5


def test_embrulhar_nao_transforma_espera_em_operacao():
    espera = sinal(action=Action.WAIT, confianca=0.4)
    envelope = EstrategiaComContexto(EstrategiaFixa(espera),
                                     contexto(RegimeDeMercado.RISCO_LIGADO))

    r = envelope.avaliar(None)

    assert r.action is Action.WAIT
    assert r.confidence == 0.4


def test_o_contexto_pode_ser_carregado_sob_demanda():
    chamadas = []

    def carregar(_):
        chamadas.append(1)
        return contexto()

    envelope = EstrategiaComContexto(EstrategiaFixa(sinal()), carregar=carregar)
    envelope.avaliar(None)

    assert chamadas == [1]
