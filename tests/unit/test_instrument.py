"""Instrumento negociavel."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cashinho.domain.instrument import Instrument


@pytest.mark.parametrize("ticker", ["PETR4", "VALE3", "BBAS3", "ITUB4", "BOVA11"])
def test_tickers_validos(ticker: str) -> None:
    assert Instrument(symbol=ticker).symbol == ticker


def test_ticker_e_normalizado_para_maiusculas() -> None:
    assert Instrument(symbol="petr4").symbol == "PETR4"


@pytest.mark.parametrize("ticker", ["PETR", "PE4", "PETR444", "PETR4X", "12345", ""])
def test_tickers_invalidos(ticker: str) -> None:
    with pytest.raises(ValidationError, match="formato esperado"):
        Instrument(symbol=ticker)


def test_lote_padrao() -> None:
    assert Instrument(symbol="PETR4").lot_size == 100


def test_lote_precisa_ser_positivo() -> None:
    with pytest.raises(ValidationError):
        Instrument(symbol="PETR4", lot_size=0)


def test_representacao_textual() -> None:
    assert str(Instrument(symbol="VALE3")) == "VALE3"
