"""O caderno onde os componentes anotam o que aconteceu com eles.

As sondas nao adivinham latencia nem erro: elas **leem** o que foi anotado
aqui. Quem faz o trabalho - baixar candle, varrer a watchlist, enviar ordem -
anota; o painel so mostra.

Um componente que nunca anotou nada aparece como sem noticias, e nao como
saudavel. Silencio nao e' sinal de vida.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Callable, Deque, Iterable, Optional

from ...models import BRT

MAX_ERROS = 20
MAX_LATENCIAS = 50


@dataclass(frozen=True)
class RegistroDeErro:
    """Um erro, com hora e origem."""

    componente: str
    mensagem: str
    quando: datetime

    def para_dict(self) -> dict:
        return {"componente": self.componente, "mensagem": self.mensagem,
                "quando": self.quando.isoformat()}


@dataclass
class Anotacoes:
    """O que se sabe de um componente."""

    erros: Deque[RegistroDeErro] = field(default_factory=lambda: deque(maxlen=MAX_ERROS))
    latencias_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=MAX_LATENCIAS))
    ultimo_ok: Optional[datetime] = None
    # ate quando o dado cobre - para candle, o FECHAMENTO dele, nao a abertura:
    # anotar a abertura embutiria um atraso fantasma do tamanho do timeframe
    ultimo_dado: Optional[datetime] = None
    detalhe: str = ""


class Telemetria:
    """Coleta as observacoes que o painel de saude usa."""

    def __init__(self, relogio: Optional[Callable[[], datetime]] = None):
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self._por_componente: dict[str, Anotacoes] = {}
        self._marcos: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    def anotacoes(self, componente: str) -> Anotacoes:
        return self._por_componente.setdefault(componente, Anotacoes())

    def conhecidos(self) -> list[str]:
        return sorted(self._por_componente)

    # -- registro --------------------------------------------------------
    def sucesso(self, componente: str, latencia_ms: Optional[float] = None,
                dado_em: Optional[datetime] = None, detalhe: str = "") -> None:
        a = self.anotacoes(componente)
        a.ultimo_ok = self._relogio()
        if latencia_ms is not None:
            a.latencias_ms.append(float(latencia_ms))
        if dado_em is not None:
            a.ultimo_dado = dado_em
        if detalhe:
            a.detalhe = detalhe

    def erro(self, componente: str, mensagem: str) -> RegistroDeErro:
        registro = RegistroDeErro(componente, str(mensagem), self._relogio())
        self.anotacoes(componente).erros.append(registro)
        return registro

    def marco(self, nome: str, quando: Optional[datetime] = None) -> datetime:
        """Marca um acontecimento do sistema (ex.: 'analise')."""
        momento = quando or self._relogio()
        self._marcos[nome] = momento
        return momento

    # -- leitura ---------------------------------------------------------
    def ultimo_marco(self, nome: str) -> Optional[datetime]:
        return self._marcos.get(nome)

    def latencia_ms(self, componente: str) -> Optional[float]:
        """Mediana das ultimas medicoes - uma leitura ruim nao vira alarme."""
        amostras = self.anotacoes(componente).latencias_ms
        return median(amostras) if amostras else None

    def erros(self, componente: str = "", desde: Optional[datetime] = None
              ) -> list[RegistroDeErro]:
        if componente:
            fonte: Iterable[RegistroDeErro] = self.anotacoes(componente).erros
        else:
            fonte = [e for a in self._por_componente.values() for e in a.erros]
        achados = [e for e in fonte if desde is None or e.quando >= desde]
        return sorted(achados, key=lambda e: e.quando, reverse=True)

    def erros_recentes(self, componente: str = "", minutos: float = 30,
                       agora: Optional[datetime] = None) -> list[RegistroDeErro]:
        instante = agora or self._relogio()
        return self.erros(componente, instante - timedelta(minutes=minutos))

    def ultimo_dado(self, componente: str) -> Optional[datetime]:
        return self.anotacoes(componente).ultimo_dado

    def ultimo_ok(self, componente: str) -> Optional[datetime]:
        return self.anotacoes(componente).ultimo_ok

    def limpar(self) -> None:
        self._por_componente.clear()
        self._marcos.clear()
