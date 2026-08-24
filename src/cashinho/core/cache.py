"""Cache com teto - porque memoizacao sem limite e' vazamento com outro nome.

Os motores de oportunidade, auditoria e confluencia guardam leituras derivadas
(estrutura de mercado, camada multi-timeframe) para nao recalcular a cada tick.
A revisao mediu: **~50 KB retidos por avaliacao**, sem nenhum limite. Uma
varredura de 20 ativos sobre um pregao inteiro passava de 400 MB.

Como o que esta guardado e' funcao **deterministica** da chave, despejar so
custa recalcular - nunca muda resultado. Por isso o teto pode ser baixo sem
medo: o padrao guarda o que uma varredura precisa e joga fora o resto.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Generic, Hashable, Iterator, TypeVar

C = TypeVar("C", bound=Hashable)
V = TypeVar("V")

TETO_PADRAO = 256


class CacheLimitado(Generic[C, V]):
    """Cache LRU simples: o menos usado recentemente sai primeiro."""

    def __init__(self, teto: int = TETO_PADRAO):
        if teto < 1:
            raise ValueError("o teto do cache precisa ser de ao menos 1 entrada")
        self.teto = teto
        self._itens: "OrderedDict[C, V]" = OrderedDict()
        self.acertos = 0
        self.faltas = 0
        self.despejos = 0

    # ------------------------------------------------------------------
    def obter(self, chave: C, calcular: Callable[[], V]) -> V:
        """Devolve o valor da chave, calculando (e guardando) se faltar."""
        if chave in self._itens:
            self.acertos += 1
            self._itens.move_to_end(chave)
            return self._itens[chave]

        self.faltas += 1
        valor = calcular()
        self._itens[chave] = valor
        while len(self._itens) > self.teto:
            self._itens.popitem(last=False)
            self.despejos += 1
        return valor

    def limpar(self) -> None:
        self._itens.clear()

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._itens)

    def __contains__(self, chave: object) -> bool:
        return chave in self._itens

    def __iter__(self) -> Iterator[C]:
        return iter(self._itens)

    @property
    def aproveitamento(self) -> float:
        """Fracao das consultas que acertaram o cache."""
        total = self.acertos + self.faltas
        return self.acertos / total if total else 0.0

    def para_dict(self) -> dict:
        return {
            "entradas": len(self._itens),
            "teto": self.teto,
            "acertos": self.acertos,
            "faltas": self.faltas,
            "despejos": self.despejos,
            "aproveitamento": round(self.aproveitamento, 3),
        }

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        return f"<CacheLimitado {len(self._itens)}/{self.teto} ({self.aproveitamento:.0%})>"
