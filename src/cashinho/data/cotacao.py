"""A cotacao padronizada - com a origem e a idade do dado grudadas nela.

Este objeto existe para que ninguem precise adivinhar de onde veio o preco
nem quando ele foi lido. Todo campo que a fonte nao entregou fica ``None``,
nunca zero: zero e' uma afirmacao sobre o mercado, ausencia nao e'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..models import BRT
from .status import StatusDados


@dataclass(frozen=True)
class Cotacao:
    """Cotacao de um ativo, normalizada, venha de onde vier."""

    symbol: str
    timestamp: datetime          # quando o dado foi apurado na fonte
    source: str                  # nome do provedor
    status: StatusDados

    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    volume: Optional[float] = None

    # os dois relogios separados: cotacao e negocio chegam em instantes
    # diferentes, e juntar os dois num campo so esconde qual esta velho
    quote_timestamp: Optional[datetime] = None
    trade_timestamp: Optional[datetime] = None

    # idade do dado em segundos, no momento da leitura. None = nao da para saber
    data_age: Optional[float] = None
    lida_em: Optional[datetime] = None
    detalhe: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "timestamp de cotacao sem fuso: o Cashinho nao mistura horario "
                "ingenuo com horario com fuso")
        for campo in ("last", "bid", "ask", "open", "high", "low", "previous_close"):
            valor = getattr(self, campo)
            if valor is not None and valor <= 0:
                raise ValueError(f"{campo} invalido ({valor}): preco precisa ser positivo")
        if self.volume is not None and self.volume < 0:
            raise ValueError(f"volume negativo ({self.volume})")

    # -- leitura -------------------------------------------------------
    @property
    def spread(self) -> Optional[float]:
        """So existe quando a fonte entrega os dois lados do book."""
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def variacao_pct(self) -> Optional[float]:
        if self.last is None or not self.previous_close:
            return None
        return (self.last / self.previous_close - 1) * 100

    @property
    def serve_para_tempo_real(self) -> bool:
        return self.status.serve_para_tempo_real

    @property
    def aviso(self) -> str:
        return self.status.aviso

    @property
    def tem_livro(self) -> bool:
        """Ha bid E ask validos agora?"""
        return self.bid is not None and self.ask is not None

    @property
    def idade_legivel(self) -> str:
        if self.data_age is None:
            return "idade desconhecida"
        if self.data_age < 1:
            return f"{self.data_age * 1000:.0f} ms"
        if self.data_age < 120:
            return f"{self.data_age:.0f} s"
        return f"{self.data_age / 60:.0f} min"

    def para_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "status": self.status.value,
            "last": self.last,
            "bid": self.bid,
            "ask": self.ask,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "previous_close": self.previous_close,
            "volume": self.volume,
            "spread": self.spread,
            "quote_timestamp": (self.quote_timestamp.isoformat()
                                if self.quote_timestamp else None),
            "trade_timestamp": (self.trade_timestamp.isoformat()
                                if self.trade_timestamp else None),
            "data_age": None if self.data_age is None else round(self.data_age, 3),
            "serve_para_tempo_real": self.serve_para_tempo_real,
            "aviso": self.aviso,
            "detalhe": self.detalhe,
        }


def cotacao_indisponivel(symbol: str, source: str, motivo: str,
                         agora: Optional[datetime] = None) -> Cotacao:
    """Cotacao que nao veio - com o motivo, sem numero nenhum."""
    instante = agora or datetime.now(BRT)
    return Cotacao(symbol=symbol.upper(), timestamp=instante, source=source,
                   status=StatusDados.OFFLINE, lida_em=instante, detalhe=motivo)
