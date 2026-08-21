"""A interface precisa mostrar pivos, suporte/resistencia e zonas de Fibonacci."""

from __future__ import annotations

from cashinho.core.structure import analisar_estrutura, grafico, painel, resumo
from cashinho.core.structure.view import CONFLUENCIA, FUNDO, LINHA_FIB, SOMBRA_FIB, TOPO

from .factories import serie_zigzag

SERIE, _ = serie_zigzag([30.0, 31.0, 30.6, 32.0, 31.6, 33.0, 32.3])
ESTRUTURA = analisar_estrutura(SERIE)


def test_painel_traz_as_quatro_secoes():
    texto = painel(ESTRUTURA)

    assert "TENDENCIA" in texto
    assert "PIVOS" in texto
    assert "SUPORTE / RESISTENCIA" in texto
    assert "FIBONACCI" in texto
    assert "EVENTOS" in texto


def test_painel_lista_pivos_com_horario_de_confirmacao():
    texto = painel(ESTRUTURA)

    assert "confirmado" in texto
    assert TOPO in texto and FUNDO in texto
    assert "[swing]" in texto


def test_painel_mostra_niveis_de_fibonacci_e_zonas():
    texto = painel(ESTRUTURA)

    for rotulo in ("23.6%", "38.2%", "50%", "61.8%", "78.6%", "127.2%", "161.8%"):
        assert rotulo in texto
    assert "zonas:" in texto
    assert "nobre" in texto


def test_painel_explica_quando_nao_ha_fibonacci():
    serie, _ = serie_zigzag([30.0, 30.02, 30.0, 30.02, 30.0, 30.02], sombra=0.005)
    texto = painel(analisar_estrutura(serie))

    assert "nao desenhado" in texto


def test_grafico_marca_pivos_e_niveis():
    texto = grafico(SERIE, ESTRUTURA, altura=14, largura=40)

    assert TOPO in texto or FUNDO in texto
    assert "R$" in texto  # eixo de precos
    assert "topo" in texto and "fundo" in texto  # legenda


def _corpo(texto: str) -> str:
    """So as linhas do desenho, sem titulo nem legenda."""
    return "\n".join(l for l in texto.splitlines() if "┤" in l)


def test_camadas_do_grafico_podem_ser_desligadas():
    completo = _corpo(grafico(SERIE, ESTRUTURA, altura=14, largura=40))
    sem_fib = _corpo(grafico(SERIE, ESTRUTURA, altura=14, largura=40, mostrar_fib=False))
    sem_pivos = _corpo(grafico(SERIE, ESTRUTURA, altura=14, largura=40, mostrar_pivos=False))
    sem_niveis = _corpo(grafico(SERIE, ESTRUTURA, altura=14, largura=40, mostrar_niveis=False))

    assert SOMBRA_FIB in completo or LINHA_FIB in completo
    assert SOMBRA_FIB not in sem_fib and LINHA_FIB not in sem_fib
    assert TOPO not in sem_pivos and FUNDO not in sem_pivos
    assert "(1x)" not in sem_niveis and "(2x)" not in sem_niveis


def test_grafico_sem_dados_avisa_em_vez_de_quebrar():
    serie, _ = serie_zigzag([30.0, 30.5], passos=1)
    assert "sem dados" in grafico(serie, analisar_estrutura(serie), altura=2)


def test_resumo_cabe_em_uma_linha():
    linha = resumo(ESTRUTURA)

    assert "\n" not in linha
    assert ESTRUTURA.symbol in linha
    assert ESTRUTURA.tendencia.regime.value in linha


def test_cores_sao_opcionais():
    sem_cor = painel(ESTRUTURA, cores=False)
    com_cor = painel(ESTRUTURA, cores=True)

    assert "\033[" not in sem_cor
    assert "\033[" in com_cor


def test_confluencia_aparece_marcada_quando_existe():
    serie, _ = serie_zigzag([30.0, 31.0, 30.2, 31.0, 30.25, 32.0, 30.6])
    e = analisar_estrutura(serie)
    if e.fib and e.fib.confluencias():
        assert CONFLUENCIA in painel(e)


def test_payload_para_interface_grafica_e_serializavel():
    import json

    dados = ESTRUTURA.para_dict()
    texto = json.dumps(dados)  # nao pode ter objeto nao serializavel

    assert '"pivos"' in texto
    assert '"suportes"' in texto and '"resistencias"' in texto
    assert dados["fibonacci"]["retracoes"][0]["rotulo"] == "23.6%"
    assert {z["nome"] for z in dados["fibonacci"]["zonas"]} >= {"rasa", "nobre", "profunda"}
