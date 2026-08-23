"""As estatisticas: aritmetica reproduzivel, sem IA."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.diario import (
    AGRUPAMENTOS,
    AMOSTRA_MINIMA,
    calcular,
    por_ativo,
    por_dia_da_semana,
    por_horario,
    por_setup,
    por_timeframe,
    todos_os_agrupamentos,
)
from cashinho.models import Direction

from .factories import BASE, registro


def _amostra():
    """Numeros redondos, conferiveis na mao."""
    return [
        registro(200.0, custos=0.0),
        registro(100.0, custos=0.0),
        registro(-50.0, custos=0.0),
        registro(-50.0, custos=0.0),
    ]


# --- os cinco agrupamentos pedidos ---------------------------------------------


def test_os_cinco_agrupamentos_existem():
    assert set(AGRUPAMENTOS) == {"setup", "ativo", "horario", "dia", "timeframe"}


def test_todos_os_agrupamentos_rodam_juntos():
    grupos = todos_os_agrupamentos(_amostra())

    assert set(grupos) == set(AGRUPAMENTOS)
    for lista in grupos.values():
        assert lista


# --- as contas ------------------------------------------------------------------


def test_as_contas_batem_na_mao():
    e = calcular(_amostra())

    assert e.n_trades == 4
    assert e.vencedores == 2 and e.perdedores == 2
    assert e.win_rate == pytest.approx(0.5)
    assert e.resultado_total == pytest.approx(200.0)
    assert e.resultado_medio == pytest.approx(50.0)
    assert e.ganho_medio == pytest.approx(150.0)
    assert e.perda_media == pytest.approx(50.0)
    assert e.payoff == pytest.approx(3.0)
    assert e.profit_factor == pytest.approx(3.0)
    assert e.expectancy == pytest.approx(0.5 * 150 - 0.5 * 50)


def test_melhor_e_pior_saem_da_amostra():
    e = calcular(_amostra())

    assert e.melhor == pytest.approx(200.0)
    assert e.pior == pytest.approx(-50.0)


def test_r_medio_e_a_media_dos_multiplos_de_risco():
    registros = [registro(180.0, quantidade=300, stop_distancia=0.30),  # 2R
                 registro(-90.0, quantidade=300, stop_distancia=0.30)]  # -1R
    e = calcular(registros)

    assert e.r_medio == pytest.approx(0.5)


def test_sem_perdas_payoff_e_pf_ficam_none():
    """Razao infinita nao vira numero bonito - vira 'nao da para calcular'."""
    e = calcular([registro(100.0), registro(50.0)])

    assert e.payoff is None
    assert e.profit_factor is None
    assert e.win_rate == 1.0


def test_amostra_vazia_nao_quebra():
    e = calcular([])

    assert e.n_trades == 0
    assert e.win_rate == 0.0
    assert e.expectancy == 0.0
    assert e.payoff is None


def test_amostra_pequena_e_sinalizada():
    assert calcular(_amostra()).amostra_pequena is True
    grande = [registro(10.0) for _ in range(AMOSTRA_MINIMA)]
    assert calcular(grande).amostra_pequena is False


# --- agrupamentos ---------------------------------------------------------------------


def test_por_setup_separa_os_grupos():
    registros = [registro(200.0, setup="pullback"), registro(-90.0, setup="rompimento"),
                 registro(100.0, setup="pullback")]
    grupos = {e.grupo: e for e in por_setup(registros)}

    assert set(grupos) == {"pullback", "rompimento"}
    assert grupos["pullback"].n_trades == 2
    assert grupos["pullback"].resultado_total == pytest.approx(300.0)


def test_por_ativo_separa_os_papeis():
    registros = [registro(200.0, symbol="PETR4"), registro(-90.0, symbol="VALE3")]
    grupos = {e.grupo for e in por_ativo(registros)}

    assert grupos == {"PETR4", "VALE3"}


def test_por_horario_usa_a_hora_da_entrada():
    registros = [registro(quando=BASE.replace(hour=10)),
                 registro(quando=BASE.replace(hour=14))]
    grupos = [e.grupo for e in por_horario(registros)]

    assert grupos == ["10h", "14h"]


def test_por_dia_da_semana_sai_na_ordem_da_semana():
    registros = [registro(quando=BASE + timedelta(days=2)),  # quarta
                 registro(quando=BASE)]                       # segunda
    grupos = [e.grupo for e in por_dia_da_semana(registros)]

    assert grupos == ["segunda", "quarta"]


def test_por_timeframe_usa_o_timeframe_do_setup():
    registros = [registro(timeframe_setup="5m"), registro(timeframe_setup="15m")]
    grupos = {e.grupo for e in por_timeframe(registros)}

    assert grupos == {"5m", "15m"}


def test_a_ordenacao_dos_grupos_e_escolhivel():
    registros = [registro(50.0, setup="a"), registro(500.0, setup="b"),
                 registro(10.0, setup="b")]

    por_resultado = [e.grupo for e in por_setup(registros, ordenar_por="resultado")]
    por_nome = [e.grupo for e in por_setup(registros, ordenar_por="grupo")]

    assert por_resultado[0] == "b"
    assert por_nome == ["a", "b"]


def test_grupo_sem_setup_recebe_rotulo_proprio():
    grupos = [e.grupo for e in por_setup([registro(setup="")])]

    assert grupos == ["(sem setup)"]


# --- sem IA, e reproduzivel ---------------------------------------------------------------


def test_o_modulo_nao_importa_nada_de_ia_nem_de_aleatoriedade():
    """A analise precisa ser estatistica e reproduzivel nesta etapa."""
    import ast
    import inspect

    from cashinho.core.diario import estatisticas

    proibidos = {"random", "numpy", "sklearn", "torch", "tensorflow", "scipy",
                 "statistics", "anthropic", "openai"}
    arvore = ast.parse(inspect.getsource(estatisticas))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes = [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            nomes = [(no.module or "").split(".")[0]]
        else:
            continue
        for nome in nomes:
            assert nome not in proibidos, f"estatisticas importa {nome}"


def test_o_mesmo_conjunto_da_sempre_o_mesmo_numero():
    registros = _amostra()

    primeira = calcular(registros).para_dict()
    segunda = calcular(list(reversed(registros))).para_dict()

    assert primeira == segunda  # a ordem nao muda a estatistica


def test_nenhuma_funcao_sugere_mudanca_de_estrategia():
    from cashinho.core.diario import estatisticas

    publicas = {n for n in dir(estatisticas) if not n.startswith("_")}
    proibidas = {"otimizar", "ajustar", "treinar", "sugerir", "recomendar", "aprender"}

    assert not (publicas & proibidas)
