"""O ticker que vai para o Yahoo."""

from __future__ import annotations

from cashinho.data.yahoo import sufixo_b3


def test_acao_da_b3_ganha_sufixo():
    assert sufixo_b3("PETR4") == "PETR4.SA"
    assert sufixo_b3("petr4") == "PETR4.SA"


def test_indice_passa_intacto():
    assert sufixo_b3("^BVSP") == "^BVSP"
    assert sufixo_b3("^GSPC") == "^GSPC"


def test_ticker_que_ja_tem_ponto_passa_intacto():
    assert sufixo_b3("PETR4.SA") == "PETR4.SA"


def test_cambio_e_futuros_nao_ganham_sufixo_da_b3():
    """USDBRL=X.SA nao existe: o download voltava vazio e o ativo sumia."""
    assert sufixo_b3("USDBRL=X") == "USDBRL=X"
    assert sufixo_b3("BZ=F") == "BZ=F"
    assert sufixo_b3("CL=F") == "CL=F"
