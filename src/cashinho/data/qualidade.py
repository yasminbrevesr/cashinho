"""Validacao da qualidade da serie que chega de qualquer provedor.

O ``Candle`` ja recusa estado impossivel um a um (maxima abaixo da minima,
preco zerado). O que ele nao consegue ver e' o que so aparece **no conjunto**:
timestamp repetido, ordem trocada, candle do futuro, buraco no meio do
pregao.

Regra da casa: **dado invalido bloqueia a analise que depende dele.** Nao ha
"corrigir" serie - so aceitar ou recusar, com o motivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from ..models import BRT, Series


class Gravidade(str, Enum):
    BLOQUEIA = "bloqueia"   # a analise nao pode rodar sobre isto
    AVISA = "avisa"         # da para usar, mas o usuario precisa saber

    @property
    def simbolo(self) -> str:
        return "✖" if self is Gravidade.BLOQUEIA else "!"


@dataclass(frozen=True)
class Problema:
    chave: str
    gravidade: Gravidade
    mensagem: str
    quantidade: int = 1

    def para_dict(self) -> dict:
        return {"chave": self.chave, "gravidade": self.gravidade.value,
                "mensagem": self.mensagem, "quantidade": self.quantidade}


@dataclass(frozen=True)
class Qualidade:
    """O veredito sobre uma serie."""

    problemas: tuple[Problema, ...] = ()
    candles: int = 0
    symbol: str = ""
    timeframe: str = ""

    @property
    def bloqueios(self) -> tuple[Problema, ...]:
        return tuple(p for p in self.problemas if p.gravidade is Gravidade.BLOQUEIA)

    @property
    def avisos(self) -> tuple[Problema, ...]:
        return tuple(p for p in self.problemas if p.gravidade is Gravidade.AVISA)

    @property
    def valida(self) -> bool:
        """Da para rodar analise sobre esta serie?"""
        return not self.bloqueios

    @property
    def rotulo(self) -> str:
        if self.bloqueios:
            return "DADOS INVALIDOS"
        if self.avisos:
            return "OK COM RESSALVAS"
        return "OK"

    def para_dict(self) -> dict:
        return {
            "rotulo": self.rotulo, "valida": self.valida, "candles": self.candles,
            "symbol": self.symbol, "timeframe": self.timeframe,
            "problemas": [p.para_dict() for p in self.problemas],
        }


@dataclass(frozen=True)
class ConfigQualidade:
    """Limiares da validacao - todos configuraveis."""

    idade_maxima_dias: Optional[float] = None   # None = nao checa idade
    folga_futuro_s: float = 60.0                # relogios nao batem ao segundo
    gap_maximo_em_candles: Optional[float] = 5.0  # buraco tolerado, em multiplos
    minimo_de_candles: int = 1


class ValidadorDeQualidade:
    """Confere a serie e devolve o veredito - nunca conserta."""

    def __init__(self, config: Optional[ConfigQualidade] = None, relogio=None):
        self.config = config or ConfigQualidade()
        self._relogio = relogio or (lambda: datetime.now(BRT))

    # ------------------------------------------------------------------
    def validar(self, serie: Series) -> Qualidade:
        cfg = self.config
        problemas: list[Problema] = []
        candles = serie.candles

        if len(candles) < max(cfg.minimo_de_candles, 1):
            problemas.append(Problema(
                "serie_vazia", Gravidade.BLOQUEIA,
                f"serie com {len(candles)} candle(s): nada a analisar"))
            return Qualidade(tuple(problemas), len(candles), serie.symbol, serie.timeframe)

        agora = self._relogio()
        ts = [c.ts for c in candles]

        # --- fuso -----------------------------------------------------
        ingenuos = sum(1 for t in ts if t.tzinfo is None)
        if ingenuos:
            problemas.append(Problema(
                "timestamp_sem_fuso", Gravidade.BLOQUEIA,
                f"{ingenuos} candle(s) sem fuso horario: misturar horario ingenuo "
                "com horario com fuso produz comparacao errada", ingenuos))
            return Qualidade(tuple(problemas), len(candles), serie.symbol, serie.timeframe)

        # --- ordem e duplicidade --------------------------------------
        fora_de_ordem = sum(1 for a, b in zip(ts, ts[1:]) if b < a)
        if fora_de_ordem:
            problemas.append(Problema(
                "fora_de_ordem", Gravidade.BLOQUEIA,
                f"{fora_de_ordem} candle(s) fora de ordem cronologica", fora_de_ordem))

        repetidos = len(ts) - len(set(ts))
        if repetidos:
            problemas.append(Problema(
                "timestamp_duplicado", Gravidade.BLOQUEIA,
                f"{repetidos} timestamp(s) repetido(s): o mesmo instante contado "
                "duas vezes vira volume e retorno inflados", repetidos))

        # --- coerencia OHLC (o Candle ja barra; aqui e' rede de seguranca)
        incoerentes = sum(
            1 for c in candles
            if not (c.high >= c.open and c.high >= c.close and c.high >= c.low
                    and c.low <= c.open and c.low <= c.close)
        )
        if incoerentes:
            problemas.append(Problema(
                "ohlc_incoerente", Gravidade.BLOQUEIA,
                f"{incoerentes} candle(s) com OHLC incoerente", incoerentes))

        nao_positivos = sum(1 for c in candles
                            if min(c.open, c.high, c.low, c.close) <= 0)
        if nao_positivos:
            problemas.append(Problema(
                "preco_nao_positivo", Gravidade.BLOQUEIA,
                f"{nao_positivos} candle(s) com preco zero ou negativo", nao_positivos))

        negativos = sum(1 for c in candles if c.volume < 0)
        if negativos:
            problemas.append(Problema(
                "volume_negativo", Gravidade.BLOQUEIA,
                f"{negativos} candle(s) com volume negativo", negativos))

        # --- futuro ----------------------------------------------------
        limite_futuro = agora + timedelta(seconds=cfg.folga_futuro_s)
        futuros = sum(1 for t in ts if t > limite_futuro)
        if futuros:
            problemas.append(Problema(
                "timestamp_futuro", Gravidade.BLOQUEIA,
                f"{futuros} candle(s) com data no futuro: operar sobre isso seria "
                "look-ahead vindo da fonte", futuros))

        # --- idade -----------------------------------------------------
        if cfg.idade_maxima_dias is not None:
            idade_dias = (agora - ts[-1]).total_seconds() / 86400
            if idade_dias > cfg.idade_maxima_dias:
                problemas.append(Problema(
                    "serie_antiga", Gravidade.AVISA,
                    f"ultimo candle tem {idade_dias:.1f} dias, acima do limite de "
                    f"{cfg.idade_maxima_dias:.1f}"))

        # --- buracos ---------------------------------------------------
        if cfg.gap_maximo_em_candles is not None and len(ts) > 2:
            problema_gap = self._gaps(ts, serie.timeframe, cfg.gap_maximo_em_candles)
            if problema_gap is not None:
                problemas.append(problema_gap)

        return Qualidade(tuple(problemas), len(candles), serie.symbol, serie.timeframe)

    # ------------------------------------------------------------------
    def _gaps(self, ts: Sequence[datetime], timeframe: str,
              maximo: float) -> Optional[Problema]:
        """Buracos maiores que o esperado *dentro do mesmo pregao*.

        Entre pregoes o buraco e' a noite, e nao e' defeito - por isso a conta
        so olha saltos dentro do mesmo dia.
        """
        from ..core.mtf.timeframes import parse_timeframe

        try:
            passo = parse_timeframe(timeframe).duracao_minutos(375) * 60
        except Exception:
            return None
        if passo <= 0:
            return None

        buracos = 0
        maior = 0.0
        for a, b in zip(ts, ts[1:]):
            if a.date() != b.date():
                continue
            salto = (b - a).total_seconds()
            if salto > passo * maximo:
                buracos += 1
                maior = max(maior, salto / passo)
        if not buracos:
            return None
        return Problema(
            "gap_inesperado", Gravidade.AVISA,
            f"{buracos} buraco(s) dentro do pregao, o maior de {maior:.0f} candles",
            buracos)
