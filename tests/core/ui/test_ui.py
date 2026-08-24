"""As pecas de tela compartilhadas."""

from __future__ import annotations

import argparse
from datetime import date, datetime

import pytest

from cashinho.core.ui import (
    PALETA,
    barra,
    barra_de_nota,
    c,
    data,
    hora,
    instante,
    largura_visivel,
    num,
    ou_traco,
    parse_hora,
    pct,
    percentuais,
    sem_cor,
)
from cashinho.models import BRT

AGORA = datetime(2026, 8, 21, 14, 30, 15, tzinfo=BRT)


# --- cores -----------------------------------------------------------------


def test_pinta_com_um_estilo():
    assert c("teste", "verde") == "\033[32mteste\033[0m"


def test_combina_estilos_na_ordem():
    assert c("teste", "verde", "negrito").startswith("\033[32m\033[1m")


def test_sem_cor_devolve_o_texto_limpo():
    """E' assim que --sem-cor funciona sem um if em cada tela."""
    assert c("teste", "verde", "negrito", ativo=False) == "teste"


def test_estilo_desconhecido_e_ignorado_e_nao_quebra():
    assert sem_cor(c("teste", "roxo-choque")) == "teste"


def test_sem_estilo_nenhum_nao_suja_o_texto():
    assert c("teste") == "teste"


def test_os_apelidos_semanticos_apontam_para_as_mesmas_cores():
    """A tela de estrutura fala alta/baixa; e' traducao, nao segunda paleta."""
    assert PALETA["alta"] == PALETA["verde"]
    assert PALETA["baixa"] == PALETA["vermelho"]
    assert PALETA["neutro"] == PALETA["amarelo"]
    assert PALETA["fraco"] == PALETA["cinza"]


def test_a_paleta_cobre_o_que_as_telas_usavam():
    for nome in ("verde", "vermelho", "amarelo", "cinza", "azul",
                 "negrito", "inverso", "reset"):
        assert nome in PALETA


def test_largura_visivel_ignora_os_codigos():
    assert largura_visivel(c("abc", "verde", "negrito")) == 3


# --- formatadores -------------------------------------------------------------


def test_numero_no_padrao_brasileiro():
    assert num(1234.5) == "1234,50"
    assert num(3.14159, casas=3) == "3,142"


def test_numero_ausente_vira_travessao():
    assert num(None) == "-"
    assert ou_traco(None) == "-"


def test_percentual_com_sinal():
    assert pct(3.14159) == "+3,14%"
    assert pct(-2.5) == "-2,50%"


def test_percentual_de_zero_nao_leva_sinal_negativo():
    """'-0,00%' e' um numero que mente sobre a direcao."""
    assert pct(-0.0001) == "0,00%"
    assert pct(0.0) == "0,00%"


def test_hora_no_mesmo_dia_e_so_a_hora():
    assert hora(AGORA, AGORA) == "14:30"
    assert hora(AGORA, AGORA, segundos=True) == "14:30:15"


def test_hora_em_outro_dia_leva_a_data():
    outro = datetime(2026, 8, 22, 10, 0, tzinfo=BRT)
    assert hora(AGORA, outro) == "21/08 14:30"


def test_hora_ausente_vira_travessao():
    assert hora(None) == "-"


def test_barra_proporcional():
    assert barra(1.0, largura=4) == "████"
    assert barra(0.0, largura=4) == "····"
    assert barra(0.5, largura=4) == "██··"


def test_barra_presa_entre_zero_e_um():
    assert barra(5.0, largura=4) == "████"
    assert barra(-2.0, largura=4) == "····"


def test_barra_de_nota_usa_escala_de_cem():
    assert barra_de_nota(100, largura=4) == "████"
    assert barra_de_nota(50, largura=4) == "██··"


# --- parsers de CLI -----------------------------------------------------------


def test_le_data_iso():
    assert data("2026-08-21") == date(2026, 8, 21)


def test_data_invalida_vira_erro_de_argumento():
    with pytest.raises(argparse.ArgumentTypeError, match="AAAA-MM-DD"):
        data("21/08/2026")


def test_instante_sem_fuso_assume_brasilia():
    assert instante("2026-08-21T14:30").utcoffset() is not None


def test_instante_com_fuso_e_respeitado():
    assert instante("2026-08-21T14:30:00-03:00").hour == 14


def test_hora_do_dia():
    from datetime import time

    assert parse_hora("10:00") == time(10, 0)
    assert parse_hora("  ") is None


def test_hora_invalida_vira_erro_de_argumento():
    with pytest.raises(argparse.ArgumentTypeError, match="HH:MM"):
        parse_hora("dez horas")


def test_percentuais_em_fracao_e_em_porcentagem():
    assert percentuais("0.6,0.2,0.2") == pytest.approx((0.6, 0.2, 0.2))
    assert percentuais("60,20,20") == pytest.approx((0.6, 0.2, 0.2))


def test_percentuais_que_nao_somam_um_nem_cem_sao_recusados():
    with pytest.raises(argparse.ArgumentTypeError, match="somam"):
        percentuais("0.5,0.5,0.5")


def test_fatia_zerada_e_recusada():
    with pytest.raises(argparse.ArgumentTypeError, match="zero"):
        percentuais("0.8,0.2,0")


# --- a duplicacao nao volta ------------------------------------------------------


def test_nenhuma_tela_tem_a_propria_paleta():
    """Antes desta extracao eram 18 copias do mesmo dicionario."""
    import pathlib

    copias = [str(p) for p in pathlib.Path("src/cashinho").rglob("*.py")
              if "_CORES = {" in p.read_text() and "/ui/" not in str(p)]

    assert copias == []


def test_nenhuma_cli_tem_o_proprio_parser_de_data():
    import pathlib
    import re

    copias = [str(p) for p in pathlib.Path("src/cashinho").rglob("__main__.py")
              if re.search(r"^def _data\(", p.read_text(), re.M)]

    assert copias == []
