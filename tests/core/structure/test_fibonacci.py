"""Fibonacci so existe quando ha swing valido - e ancorado nos pivos dele."""

from __future__ import annotations

import pytest

from cashinho.core.structure import (
    EstruturaConfig,
    Level,
    Pivot,
    Swing,
    TipoPivo,
    analisar_estrutura,
    constroi_fibonacci,
    preco_da_razao,
)

from .factories import serie_zigzag, ts

CFG = EstruturaConfig()

RAZOES_RETRACAO = (0.236, 0.382, 0.5, 0.618, 0.786)
RAZOES_EXTENSAO = (1.272, 1.618)


def _pivo(indice: int, preco: float, tipo: TipoPivo) -> Pivot:
    return Pivot(
        indice=indice,
        ts=ts(10, indice),
        preco=preco,
        tipo=tipo,
        indice_confirmacao=indice + 2,
        ts_confirmacao=ts(10, indice + 2),
        significativo=True,
    )


def _swing(origem: float, extremo: float, valido: bool = True) -> Swing:
    tipo_inicio = TipoPivo.FUNDO if extremo > origem else TipoPivo.TOPO
    return Swing(
        inicio=_pivo(0, origem, tipo_inicio),
        fim=_pivo(10, extremo, tipo_inicio.oposto),
        amplitude=abs(extremo - origem),
        amplitude_atr=3.0,
        amplitude_pct=5.0,
        duracao=10,
        valido=valido,
    )


# ---------------------------------------------------------------------------
# so com swing valido
# ---------------------------------------------------------------------------


def test_sem_swing_nao_existe_fibonacci():
    assert constroi_fibonacci(None, [], 0.35, CFG) is None


def test_swing_invalido_nao_desenha_fibonacci():
    assert constroi_fibonacci(_swing(30.0, 32.0, valido=False), [], 0.35, CFG) is None


def test_ruido_sem_perna_relevante_nao_gera_grade():
    """Oscilacao de centavos nao e' swing: nao ha o que ancorar."""
    serie, _ = serie_zigzag([30.0, 30.02, 30.0, 30.02, 30.0, 30.02], sombra=0.005)
    e = analisar_estrutura(serie, CFG)

    assert e.swing_valido is None
    assert e.fib is None
    assert e.motivo_sem_fib
    assert "amplitude" in e.motivo_sem_fib or "perna" in e.motivo_sem_fib


def test_swing_valido_gera_grade_ancorada_nos_pivos():
    serie, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0])
    e = analisar_estrutura(serie, CFG)

    assert e.swing_valido is not None
    assert e.fib is not None
    assert e.fib.ancora_100 == pytest.approx(e.swing_valido.inicio.preco)
    assert e.fib.ancora_0 == pytest.approx(e.swing_valido.fim.preco)
    assert e.fib.swing is e.swing_valido


# ---------------------------------------------------------------------------
# precos exatos
# ---------------------------------------------------------------------------


def test_retracoes_de_uma_perna_de_alta():
    """Perna de 30,50 ate 32,00 (amplitude 1,50): retracoes descem do topo."""
    grade = constroi_fibonacci(_swing(30.50, 32.00), [], 0.35, CFG)

    esperado = {
        0.236: 32.00 - 1.50 * 0.236,
        0.382: 32.00 - 1.50 * 0.382,
        0.500: 32.00 - 1.50 * 0.500,
        0.618: 32.00 - 1.50 * 0.618,
        0.786: 32.00 - 1.50 * 0.786,
    }
    for razao, preco in esperado.items():
        assert grade.nivel(razao).preco == pytest.approx(preco)


def test_extensoes_de_uma_perna_de_alta_projetam_acima_do_topo():
    grade = constroi_fibonacci(_swing(30.50, 32.00), [], 0.35, CFG)

    assert grade.nivel(1.272).preco == pytest.approx(30.50 + 1.50 * 1.272)
    assert grade.nivel(1.618).preco == pytest.approx(30.50 + 1.50 * 1.618)
    assert grade.nivel(1.272).preco > 32.00


def test_perna_de_baixa_espelha_a_grade():
    """De 32,00 para 30,50: retracao sobe, extensao projeta abaixo do fundo."""
    grade = constroi_fibonacci(_swing(32.00, 30.50), [], 0.35, CFG)

    assert grade.nivel(0.5).preco == pytest.approx(30.50 + 1.50 * 0.5)
    assert grade.nivel(0.618).preco == pytest.approx(30.50 + 1.50 * 0.618)
    assert grade.nivel(1.618).preco == pytest.approx(32.00 - 1.50 * 1.618)
    assert grade.nivel(1.618).preco < 30.50


def test_todas_as_razoes_pedidas_estao_presentes():
    grade = constroi_fibonacci(_swing(30.0, 33.0), [], 0.35, CFG)

    assert tuple(n.razao for n in grade.retracoes) == RAZOES_RETRACAO
    assert tuple(n.razao for n in grade.extensoes) == RAZOES_EXTENSAO
    assert [n.rotulo for n in grade.retracoes] == ["23.6%", "38.2%", "50%", "61.8%", "78.6%"]
    assert [n.rotulo for n in grade.extensoes] == ["127.2%", "161.8%"]


def test_razao_zero_e_cem_por_cento_sao_as_ancoras():
    swing = _swing(30.0, 33.0)
    assert preco_da_razao(swing, 0.0) == pytest.approx(33.0)
    assert preco_da_razao(swing, 1.0) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# zonas e confluencia
# ---------------------------------------------------------------------------


def test_zonas_cobrem_as_faixas_classicas():
    grade = constroi_fibonacci(_swing(30.0, 32.0), [], 0.35, CFG)
    zonas = {z.nome: z for z in grade.zonas}

    assert set(zonas) == {"rasa", "nobre", "profunda", "alvos"}
    nobre = zonas["nobre"]
    assert nobre.low == pytest.approx(preco_da_razao(grade.swing, 0.618))
    assert nobre.high == pytest.approx(preco_da_razao(grade.swing, 0.382))
    assert nobre.contem(31.0)  # 50% da perna


def test_faixa_de_pullback_nao_tem_buracos_entre_as_zonas():
    """Qualquer retracao entre 23,6% e 78,6% cai em exatamente uma zona."""
    grade = constroi_fibonacci(_swing(30.0, 32.0), [], 0.35, CFG)

    for passo in range(24, 79):
        preco = preco_da_razao(grade.swing, passo / 100)
        assert grade.zona_do_preco(preco) is not None, f"retracao {passo}% ficou sem zona"


def test_zona_do_preco_identifica_onde_o_mercado_esta():
    grade = constroi_fibonacci(_swing(30.0, 32.0), [], 0.35, CFG)

    assert grade.zona_do_preco(31.0).nome == "nobre"  # 50% da perna
    assert grade.zona_do_preco(31.4).nome == "rasa"  # ~30% da perna
    assert grade.zona_do_preco(31.9) is None  # correcao rasa demais, fora das zonas
    assert grade.zona_do_preco(29.0) is None  # abaixo da origem da perna


def test_nivel_de_fibonacci_marca_confluencia_com_suporte():
    swing = _swing(30.0, 32.0)
    preco_618 = preco_da_razao(swing, 0.618)
    suporte = Level(
        low=preco_618 - 0.02,
        high=preco_618 + 0.02,
        tipo="suporte",
        toques=3,
        forca=0.8,
        ultimo_toque=ts(11, 0),
    )

    grade = constroi_fibonacci(swing, [suporte], 0.35, CFG)
    nivel = grade.nivel(0.618)

    assert nivel.tem_confluencia
    assert nivel.confluencia is suporte
    assert grade.confluencias()


def test_razoes_sao_configuraveis():
    cfg = EstruturaConfig(retracoes=(0.5,), extensoes=(2.0,))
    grade = constroi_fibonacci(_swing(30.0, 32.0), [], 0.35, cfg)

    assert [n.razao for n in grade.retracoes] == [0.5]
    assert [n.razao for n in grade.extensoes] == [2.0]
    assert {z.nome for z in grade.zonas} == set()  # sem as razoes das zonas, nao ha zona
