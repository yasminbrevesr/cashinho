"""Provedor de dados a partir de arquivos CSV exportados (Profit, MetaTrader, corretora).

Formato esperado: uma coluna de data/hora e as colunas OHLCV. Os nomes das
colunas sao reconhecidos em portugues e ingles, por exemplo::

    data,abertura,maxima,minima,fechamento,volume
    2026-08-20 10:00:00,31.10,31.28,31.05,31.22,1520000

Coloque um arquivo por ativo/timeframe na pasta de dados, com o nome
``PETR4_5m.csv`` (ou ``PETR4.csv`` quando houver um unico timeframe).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import BRT, Candle, Series
from .base import DataError, Provider

_ALIAS = {
    "ts": {"ts", "data", "datahora", "datetime", "date", "time", "data_hora", "timestamp"},
    "open": {"open", "abertura", "abre", "o"},
    "high": {"high", "maxima", "máxima", "max", "h"},
    "low": {"low", "minima", "mínima", "min", "l"},
    "close": {"close", "fechamento", "fecha", "ultimo", "último", "c"},
    "volume": {"volume", "vol", "quantidade", "qtd", "v", "negocios"},
}

_FORMATOS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def _normaliza(nome: str) -> str:
    return nome.strip().lower().replace(" ", "").replace("-", "_")


def _mapa_colunas(cabecalho: list[str]) -> dict[str, int]:
    mapa: dict[str, int] = {}
    for i, col in enumerate(cabecalho):
        n = _normaliza(col)
        for campo, aliases in _ALIAS.items():
            if n in aliases and campo not in mapa:
                mapa[campo] = i
    faltando = {"ts", "open", "high", "low", "close"} - set(mapa)
    if faltando:
        raise DataError(f"CSV sem as colunas: {', '.join(sorted(faltando))}")
    return mapa


def _para_datetime(txt: str) -> datetime:
    txt = txt.strip()
    for f in _FORMATOS:
        try:
            return datetime.strptime(txt, f).replace(tzinfo=BRT)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(txt)
        return d if d.tzinfo else d.replace(tzinfo=BRT)
    except ValueError as e:
        raise DataError(f"data invalida no CSV: {txt!r}") from e


def _para_float(txt: str) -> float:
    t = txt.strip().replace("R$", "").replace(" ", "")
    if not t:
        return 0.0
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


class CSVProvider(Provider):
    nome = "csv"

    def __init__(self, pasta: str | Path):
        self.pasta = Path(pasta)
        if not self.pasta.exists():
            raise DataError(f"pasta de CSVs nao encontrada: {self.pasta}")

    def _arquivo(self, symbol: str, timeframe: str) -> Path:
        s = symbol.upper()
        candidatos = [
            self.pasta / f"{s}_{timeframe}.csv",
            self.pasta / f"{s}-{timeframe}.csv",
            self.pasta / f"{s}.csv",
            self.pasta / f"{s.lower()}_{timeframe}.csv",
            self.pasta / f"{s.lower()}.csv",
        ]
        for c in candidatos:
            if c.exists():
                return c
        raise DataError(f"CSV nao encontrado para {s} ({timeframe}) em {self.pasta}")

    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        arq = self._arquivo(symbol, timeframe)
        with arq.open(newline="", encoding="utf-8-sig") as fh:
            amostra = fh.read(4096)
            fh.seek(0)
            try:
                dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
            except csv.Error:
                dialeto = csv.excel
            leitor = csv.reader(fh, dialeto)
            linhas = [l for l in leitor if l]
        if len(linhas) < 2:
            raise DataError(f"CSV vazio: {arq}")
        mapa = _mapa_colunas(linhas[0])
        candles: list[Candle] = []
        for linha in linhas[1:]:
            if len(linha) <= max(mapa.values()):
                continue
            try:
                candles.append(
                    Candle(
                        _para_datetime(linha[mapa["ts"]]),
                        _para_float(linha[mapa["open"]]),
                        _para_float(linha[mapa["high"]]),
                        _para_float(linha[mapa["low"]]),
                        _para_float(linha[mapa["close"]]),
                        _para_float(linha[mapa["volume"]]) if "volume" in mapa else 0.0,
                    )
                )
            except (DataError, ValueError):
                continue
        if not candles:
            raise DataError(f"nenhum candle valido em {arq}")
        candles.sort(key=lambda c: c.ts)
        if dias:
            ultimo_dia = candles[-1].ts.astimezone(BRT).date()
            limite = ultimo_dia.toordinal() - dias
            candles = [c for c in candles if c.ts.astimezone(BRT).date().toordinal() > limite]
        return Series(symbol.upper(), timeframe, candles)
