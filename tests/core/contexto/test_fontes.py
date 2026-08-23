"""As fontes: o que elas atendem, e o que fazem quando falham."""

from __future__ import annotations

import json

import pytest

from cashinho.core.contexto import (
    DOLAR,
    IBOVESPA,
    JUROS_CDI,
    MINERIO,
    FonteBCB,
    FonteComposta,
    FonteProvider,
    fonte_demo,
)
from cashinho.data.base import DataError, Provider
from cashinho.models import Series

from .factories import FonteFalsa, serie


class ProviderFalso(Provider):
    nome = "yahoo"

    def __init__(self, falhar: bool = False):
        self.falhar = falhar
        self.pedidos: list[tuple[str, str, int]] = []

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        self.pedidos.append((symbol, timeframe, dias))
        if self.falhar:
            raise DataError("sem dados")
        return serie([100.0, 101.0], symbol=symbol)


# --- provider adaptado ---------------------------------------------------------


def test_o_ticker_vem_do_catalogo_e_nao_da_adivinhacao():
    provider = ProviderFalso()
    FonteProvider(provider).serie(DOLAR, "60m", 5)

    assert provider.pedidos[0][0] == "USDBRL=X"


def test_a_fonte_so_atende_quem_tem_ticker_dela():
    fonte = FonteProvider(ProviderFalso())

    assert fonte.atende(IBOVESPA) is True
    assert fonte.atende(JUROS_CDI) is False  # juros nao esta no Yahoo
    assert fonte.atende(MINERIO) is False


def test_pedir_instrumento_que_a_fonte_nao_atende_levanta():
    with pytest.raises(DataError, match="nao atende"):
        FonteProvider(ProviderFalso()).serie(MINERIO, "60m", 5)


# --- Banco Central --------------------------------------------------------------


def _sgs(linhas):
    return lambda url: json.dumps(linhas)


def test_le_a_serie_do_sgs():
    fonte = FonteBCB(abrir=_sgs([
        {"data": "20/08/2026", "valor": "10.65"},
        {"data": "21/08/2026", "valor": "10.65"},
    ]))
    s = fonte.serie(JUROS_CDI, "1d", 5)

    assert len(s) == 2
    assert s.price == 10.65
    assert s.timeframe == "1d"


def test_aceita_o_decimal_com_virgula():
    fonte = FonteBCB(abrir=_sgs([{"data": "21/08/2026", "valor": "10,65"}]))

    assert fonte.serie(JUROS_CDI, "1d", 5).price == 10.65


def test_linha_estranha_e_descartada_e_nao_corrigida():
    fonte = FonteBCB(abrir=_sgs([
        {"data": "20/08/2026", "valor": "10.65"},
        {"data": "sem data", "valor": "x"},
    ]))

    assert len(fonte.serie(JUROS_CDI, "1d", 5)) == 1


def test_resposta_vazia_vira_erro_e_nao_serie_vazia():
    with pytest.raises(DataError, match="sem valores"):
        FonteBCB(abrir=_sgs([])).serie(JUROS_CDI, "1d", 5)


def test_resposta_que_nao_e_json_vira_erro():
    with pytest.raises(DataError, match="JSON"):
        FonteBCB(abrir=lambda url: "<html>manutencao</html>").serie(JUROS_CDI, "1d", 5)


def test_falha_de_rede_vira_data_error():
    def explode(url):
        raise OSError("sem rede")

    with pytest.raises(DataError, match="falha ao consultar"):
        FonteBCB(abrir=explode).serie(JUROS_CDI, "1d", 5)


def test_a_url_do_sgs_usa_o_codigo_da_serie():
    vistas = []

    def espiao(url):
        vistas.append(url)
        return json.dumps([{"data": "21/08/2026", "valor": "1"}])

    FonteBCB(abrir=espiao).serie(JUROS_CDI, "1d", 5)

    assert "bcdata.sgs.12" in vistas[0]
    assert vistas[0].startswith("https://api.bcb.gov.br/")


# --- composicao ------------------------------------------------------------------


def test_a_composta_usa_a_fonte_que_atende_cada_instrumento():
    yahoo = FonteProvider(ProviderFalso())
    bcb = FonteBCB(abrir=_sgs([{"data": "21/08/2026", "valor": "10.65"}]))
    composta = FonteComposta([yahoo, bcb])

    assert composta.serie(IBOVESPA, "60m", 5).price == 101.0
    assert composta.serie(JUROS_CDI, "1d", 5).price == 10.65


def test_a_composta_tenta_a_proxima_quando_a_primeira_falha():
    ruim = FonteFalsa(erros={"ibovespa": "caiu"})
    boa = FonteFalsa({"ibovespa": serie([10.0, 11.0])})

    assert FonteComposta([ruim, boa]).serie(IBOVESPA, "60m", 5).price == 11.0


def test_a_composta_junta_os_erros_quando_todas_falham():
    a = FonteFalsa(erros={"ibovespa": "erro A"})
    b = FonteFalsa(erros={"ibovespa": "erro B"})

    with pytest.raises(DataError) as e:
        FonteComposta([a, b]).serie(IBOVESPA, "60m", 5)
    assert "erro A" in str(e.value) and "erro B" in str(e.value)


def test_a_composta_nao_atende_o_que_ninguem_atende():
    assert FonteComposta([FonteFalsa()]).atende(MINERIO) is False


def test_composta_vazia_e_recusada():
    with pytest.raises(ValueError):
        FonteComposta([])


# --- demonstracao -------------------------------------------------------------------


def test_a_fonte_demo_se_declara_simulada():
    assert fonte_demo().simulada is True


def test_a_fonte_demo_nao_inventa_o_que_nao_tem_fonte():
    """Nem a demonstracao pode gerar minerio: o instrumento nao tem fonte."""
    assert fonte_demo().atende(MINERIO) is False


def test_a_fonte_demo_e_deterministica():
    a = fonte_demo(semente=3).serie(IBOVESPA, "60m", 5)
    b = fonte_demo(semente=3).serie(IBOVESPA, "60m", 5)

    assert a.closes == b.closes
