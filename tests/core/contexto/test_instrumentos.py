"""O catalogo: um instrumento so existe com a fonte declarada."""

from __future__ import annotations

import pytest

from cashinho.core.contexto import (
    CATALOGO,
    DOLAR,
    IBOVESPA,
    JUROS_CDI,
    MINERIO,
    NASDAQ,
    PETROLEO,
    SP500,
    Papel,
    instrumento,
    sem_fonte_confiavel,
)


def test_o_catalogo_cobre_o_que_foi_pedido():
    papeis = {i.papel for i in CATALOGO}
    assert papeis == {
        Papel.INDICE_LOCAL, Papel.CAMBIO, Papel.JUROS,
        Papel.COMMODITY, Papel.INDICE_INTERNACIONAL,
    }
    chaves = {i.chave for i in CATALOGO}
    assert {"ibovespa", "dolar", "juros", "petroleo", "minerio"} <= chaves
    assert len([i for i in CATALOGO if i.papel is Papel.INDICE_INTERNACIONAL]) >= 2


def test_todo_instrumento_com_fonte_tem_ticker_declarado():
    for i in CATALOGO:
        if i.tem_fonte:
            assert all(t.strip() for t in i.tickers.values())


def test_o_que_nao_tem_fonte_confiavel_fica_declarado_e_nao_estimado():
    """Minerio nao tem fonte publica confiavel - e o catalogo diz isso."""
    assert MINERIO.tem_fonte is False
    assert "FONTE A CONFIRMAR" in MINERIO.observacao
    assert MINERIO in sem_fonte_confiavel()


def test_nenhum_instrumento_sem_fonte_ganha_ticker_por_engano():
    for i in sem_fonte_confiavel():
        assert i.tickers == {}
        assert i.observacao, f"{i.chave} precisa dizer por que nao tem fonte"


def test_tickers_do_yahoo_sao_os_reais():
    assert IBOVESPA.ticker("yahoo") == "^BVSP"
    assert DOLAR.ticker("yahoo") == "USDBRL=X"
    assert SP500.ticker("yahoo") == "^GSPC"
    assert NASDAQ.ticker("yahoo") == "^IXIC"
    assert PETROLEO.ticker("yahoo") == "BZ=F"


def test_juros_vem_do_banco_central_e_nao_e_intradiario():
    assert JUROS_CDI.ticker("bcb") == "12"
    assert JUROS_CDI.ticker("yahoo") is None
    assert JUROS_CDI.intradiario is False


def test_busca_por_chave():
    assert instrumento("ibovespa") is IBOVESPA
    with pytest.raises(KeyError, match="desconhecido"):
        instrumento("bitcoin")
