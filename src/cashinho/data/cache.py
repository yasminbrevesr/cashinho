"""Cache simples em disco para nao repetir chamadas ao provedor em modo monitor."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from ..models import BRT, Candle, Series

from datetime import datetime

PASTA_PADRAO = Path(os.environ.get("CASHINHO_CACHE", Path(tempfile.gettempdir()) / "cashinho-cache"))


class Cache:
    def __init__(self, pasta: Path = PASTA_PADRAO, ttl_segundos: int = 45):
        self.pasta = Path(pasta)
        self.ttl = ttl_segundos
        self.pasta.mkdir(parents=True, exist_ok=True)

    def _arquivo(self, chave: str) -> Path:
        seguro = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in chave)
        return self.pasta / f"{seguro}.json"

    def obter(self, chave: str) -> Optional[Series]:
        f = self._arquivo(chave)
        if not f.exists():
            return None
        if time.time() - f.stat().st_mtime > self.ttl:
            return None
        try:
            dados = json.loads(f.read_text())
            candles = [
                Candle(
                    datetime.fromisoformat(c["ts"]).astimezone(BRT),
                    c["o"], c["h"], c["l"], c["c"], c["v"],
                )
                for c in dados["candles"]
            ]
            return Series(dados["symbol"], dados["timeframe"], candles)
        except Exception:
            return None

    def guardar(self, chave: str, serie: Series) -> None:
        dados = {
            "symbol": serie.symbol,
            "timeframe": serie.timeframe,
            "candles": [
                {"ts": c.ts.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
                for c in serie.candles
            ],
        }
        try:
            self._arquivo(chave).write_text(json.dumps(dados))
        except OSError:
            pass

    def limpar(self) -> None:
        for f in self.pasta.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass
