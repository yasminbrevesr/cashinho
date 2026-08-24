"""Fuso do servidor da Genial e resolucao de simbolo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cashinho.data.metatrader import (
    NormalizadorDeTempoDoBroker,
    Resolucao,
    SimboloAmbiguoError,
    SimboloNaoEncontradoError,
    resolver,
)
from cashinho.models import BRT

from .factories import SIMBOLOS_GENIAL, epoch_do_servidor


# ---------------------------------------------------------------------------
# o deslocamento de 3 horas
# ---------------------------------------------------------------------------


def test_o_relogio_do_servidor_e_preservado():
    """17:05 no terminal da Genial precisa virar 17:05 no Cashinho."""
    n = NormalizadorDeTempoDoBroker()
    bruto = datetime(2026, 8, 21, 17, 5, tzinfo=timezone.utc).timestamp()

    convertido = n.de_epoch(bruto)

    assert convertido.hour == 17
    assert convertido.minute == 5


def test_a_conversao_ingenua_erraria_em_tres_horas():
    """O erro que o normalizador existe para impedir, escrito como teste."""
    n = NormalizadorDeTempoDoBroker()
    bruto = datetime(2026, 8, 21, 17, 5, tzinfo=timezone.utc).timestamp()

    certo = n.de_epoch(bruto)
    ingenuo = datetime.fromtimestamp(bruto, tz=timezone.utc).astimezone(BRT)

    assert certo.hour - ingenuo.hour == 3
    assert certo.hour == 17 and ingenuo.hour == 14


def test_o_resultado_sempre_tem_fuso():
    n = NormalizadorDeTempoDoBroker()

    assert n.de_epoch(epoch_do_servidor(datetime(2026, 8, 21, 10, 0, tzinfo=BRT))).tzinfo


def test_milissegundos_tambem_sao_normalizados():
    n = NormalizadorDeTempoDoBroker()
    momento = datetime(2026, 8, 21, 17, 32, 41, tzinfo=BRT)
    bruto_ms = epoch_do_servidor(momento) * 1000 + 596

    convertido = n.de_epoch_ms(bruto_ms)

    assert convertido.hour == 17 and convertido.minute == 32
    assert convertido.second == 41
    assert 590 <= convertido.microsecond / 1000 <= 600


def test_a_ida_e_a_volta_batem():
    n = NormalizadorDeTempoDoBroker()
    momento = datetime(2026, 8, 21, 14, 30, tzinfo=BRT)

    assert n.de_epoch(n.para_epoch(momento)) == momento


def test_horario_ingenuo_e_recusado_na_volta():
    n = NormalizadorDeTempoDoBroker()

    with pytest.raises(ValueError, match="sem fuso"):
        n.para_epoch(datetime(2026, 8, 21, 14, 30))


def test_o_fuso_do_servidor_e_configuravel():
    n = NormalizadorDeTempoDoBroker(fuso_do_servidor="America/Sao_Paulo")

    assert n.para_dict()["fuso_do_servidor"] == "America/Sao_Paulo"


def test_o_agora_do_servidor_usa_o_fuso_dele():
    n = NormalizadorDeTempoDoBroker()
    agora = datetime(2026, 8, 21, 14, 30, tzinfo=BRT)

    assert n.agora_no_servidor(agora).hour == 14


# ---------------------------------------------------------------------------
# resolucao de simbolo
# ---------------------------------------------------------------------------


def test_petr4_casa_exatamente():
    r = resolver("PETR4", SIMBOLOS_GENIAL)

    assert r.resolvido == "PETR4"
    assert r.exato is True


def test_a_exata_vence_mesmo_havendo_sufixados():
    """PETR4F, PETR4T, PETR4M... nao podem roubar a vez de PETR4."""
    assert resolver("PETR4", SIMBOLOS_GENIAL).resolvido == "PETR4"


def test_minusculo_e_espaco_nao_atrapalham():
    assert resolver("  petr4 ", SIMBOLOS_GENIAL).resolvido == "PETR4"


def test_prefixo_ambiguo_e_erro_e_nao_escolha():
    """Escolher em silencio seria analisar outro instrumento."""
    with pytest.raises(SimboloAmbiguoError) as e:
        resolver("PETR", SIMBOLOS_GENIAL)

    assert "SYMBOL_AMBIGUOUS" in str(e.value)
    assert "PETR4F" in str(e.value)


def test_simbolo_inexistente_e_erro_nomeado():
    with pytest.raises(SimboloNaoEncontradoError, match="SYMBOL_NOT_FOUND"):
        resolver("XPTO9", SIMBOLOS_GENIAL)


def test_ticker_vazio_e_recusado():
    with pytest.raises(SimboloNaoEncontradoError):
        resolver("   ", SIMBOLOS_GENIAL)


def test_aproximado_so_com_um_candidato_e_so_quando_pedido():
    assert resolver("VALE", SIMBOLOS_GENIAL, permitir_aproximado=True).resolvido == "VALE3"

    with pytest.raises(SimboloAmbiguoError):
        resolver("PETR", SIMBOLOS_GENIAL, permitir_aproximado=True)


def test_aproximado_marca_que_nao_foi_exato():
    r = resolver("VALE", SIMBOLOS_GENIAL, permitir_aproximado=True)

    assert r.exato is False
    assert r.candidatos == ("VALE3",)


# ---------------------------------------------------------------------------
# a cadeia completa: MT5 -> horario do servidor -> instante em UTC
# ---------------------------------------------------------------------------


def test_a_cadeia_completa_do_enunciado():
    """17:05 no MT5 -> 17:05 America/Sao_Paulo -> 20:05 UTC.

    Os dois ultimos passos sao o MESMO instante escrito de dois jeitos: o
    dominio carrega -03:00, e quem quiser ver em UTC so converte. O que nao
    pode e' o primeiro passo escorregar para 14:05.
    """
    n = NormalizadorDeTempoDoBroker()
    bruto = datetime(2026, 8, 21, 17, 5, tzinfo=timezone.utc).timestamp()

    no_dominio = n.de_epoch(bruto)
    em_utc = no_dominio.astimezone(timezone.utc)

    assert (no_dominio.hour, no_dominio.minute) == (17, 5)      # Sao Paulo
    assert (em_utc.hour, em_utc.minute) == (20, 5)              # UTC
    assert no_dominio == em_utc                                 # mesmo instante


def test_o_deslocamento_do_dominio_e_de_tres_horas():
    n = NormalizadorDeTempoDoBroker()
    momento = n.de_epoch(epoch_do_servidor(datetime(2026, 8, 21, 17, 5, tzinfo=BRT)))

    assert momento.utcoffset().total_seconds() == -3 * 3600


def test_toda_normalizacao_sai_com_fuso_nunca_ingenua():
    """A regra do projeto: nada de horario sem fuso circulando."""
    n = NormalizadorDeTempoDoBroker()
    for hora in (10, 13, 17, 23):
        bruto = datetime(2026, 8, 21, hora, 0, tzinfo=timezone.utc).timestamp()
        assert n.de_epoch(bruto).tzinfo is not None


def test_a_logica_de_fuso_esta_so_no_normalizador():
    """Nao pode haver conversao de epoch espalhada pelo adapter."""
    import ast
    import pathlib

    culpados = []
    for arquivo in pathlib.Path("src/cashinho/data/metatrader").glob("*.py"):
        if arquivo.name == "tempo.py":
            continue
        arvore = ast.parse(arquivo.read_text())
        nomes = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
        if {"fromtimestamp", "utcfromtimestamp"} & nomes:
            culpados.append(arquivo.name)

    assert culpados == []
