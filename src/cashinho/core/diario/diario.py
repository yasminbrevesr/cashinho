"""O diario: guarda, filtra e resume as operacoes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ...models import BRT
from .estatisticas import Estatistica, calcular, todos_os_agrupamentos
from .modelos import Filtro, Registro


class DiarioDeTrades:
    """Colecao de registros, com filtro e estatistica.

    O arquivo e' JSONL - uma operacao por linha. Formato de diario mesmo:
    novas linhas so entram no fim, e um registro antigo nunca e' reescrito.
    """

    def __init__(self, registros: Optional[Iterable[Registro]] = None):
        self._registros: list[Registro] = list(registros or [])

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._registros)

    def __iter__(self):
        return iter(self._registros)

    @property
    def registros(self) -> list[Registro]:
        return list(self._registros)

    def registrar(self, registro: Registro) -> Registro:
        self._registros.append(registro)
        return registro

    def filtrar(self, filtro: Optional[Filtro] = None) -> list[Registro]:
        """Aplica o recorte e devolve em ordem cronologica."""
        if filtro is None or filtro.vazio:
            selecionados = list(self._registros)
        else:
            selecionados = [r for r in self._registros if filtro.aceita(r)]
        return sorted(selecionados, key=lambda r: (r.aberta_em, r.symbol))

    # ------------------------------------------------------------------
    def estatistica(self, filtro: Optional[Filtro] = None) -> Estatistica:
        return calcular(self.filtrar(filtro), grupo="total")

    def agrupamentos(self, filtro: Optional[Filtro] = None) -> dict[str, list[Estatistica]]:
        """As cinco visoes: setup, ativo, horario, dia da semana e timeframe."""
        return todos_os_agrupamentos(self.filtrar(filtro))

    def ativos(self) -> list[str]:
        return sorted({r.symbol for r in self._registros})

    def setups(self) -> list[str]:
        return sorted({r.setup for r in self._registros if r.setup})

    def periodo(self) -> Optional[tuple[date, date]]:
        if not self._registros:
            return None
        datas = [r.data for r in self._registros]
        return min(datas), max(datas)

    # ------------------------------------------------------------------
    # persistencia
    # ------------------------------------------------------------------
    def salvar(self, caminho: str | Path) -> Path:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8") as fh:
            for r in self._registros:
                fh.write(json.dumps(r.para_dict(), ensure_ascii=False) + "\n")
        return destino

    def anexar(self, caminho: str | Path, registro: Registro) -> Path:
        """Acrescenta uma linha sem reescrever o arquivo inteiro."""
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(registro.para_dict(), ensure_ascii=False) + "\n")
        return destino

    @classmethod
    def carregar(cls, caminho: str | Path) -> "DiarioDeTrades":
        origem = Path(caminho)
        if not origem.exists():
            return cls()
        registros = []
        for linha in origem.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha:
                continue
            try:
                registros.append(Registro.de_dict(json.loads(linha)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # linha corrompida nao derruba o diario inteiro
        return cls(registros)

    def para_dict(self, filtro: Optional[Filtro] = None) -> dict:
        selecionados = self.filtrar(filtro)
        return {
            "total_de_registros": len(self._registros),
            "filtrados": len(selecionados),
            "filtro": (filtro or Filtro()).descricao(),
            "estatistica": calcular(selecionados, "total").para_dict(),
            "agrupamentos": {
                nome: [e.para_dict() for e in lista]
                for nome, lista in todos_os_agrupamentos(selecionados).items()
            },
            "registros": [r.para_dict() for r in selecionados],
        }
