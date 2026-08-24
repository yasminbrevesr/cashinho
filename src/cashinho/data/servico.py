"""``MarketDataService``: quem escolhe o provedor por **finalidade**.

    BACKTEST, RESEARCH, DASHBOARD historico  -> provedor HISTORICO
    SCANNER INTRADAY, PAPER ao vivo          -> provedor TEMPO REAL

A separacao por finalidade e' o coracao desta camada. Um provedor gratuito e
atrasado e' otimo para backtest e imprestavel para decidir entrada agora - e
quem sabe a diferenca e' este servico, nao a estrategia.

**Nao ha fallback silencioso.** Se o provedor de tempo real cair durante o
pregao, o servico nao troca por dado atrasado fingindo que e' mercado: ele
recusa, e o motivo aparece na tela.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Mapping, Optional

from ..models import BRT, Series
from .base import DataError, Provider
from .cotacao import Cotacao
from .mercado import MarketDataProvider
from .qualidade import ConfigQualidade, Qualidade, ValidadorDeQualidade
from .status import Capacidades, CapacidadeAusenteError, StatusDados


class Finalidade(str, Enum):
    """Para que o dado vai ser usado - e' isso que decide o provedor."""

    BACKTEST = "backtest"
    PESQUISA = "pesquisa"
    HISTORICO = "historico"
    SCANNER_INTRADIARIO = "scanner_intradiario"
    PAPER_AO_VIVO = "paper_ao_vivo"
    ANALISE_ASSISTIDA = "analise_assistida"

    @property
    def exige_tempo_real(self) -> bool:
        return self in (Finalidade.SCANNER_INTRADIARIO, Finalidade.PAPER_AO_VIVO,
                        Finalidade.ANALISE_ASSISTIDA)

    @property
    def rotulo(self) -> str:
        return {
            "backtest": "Backtest", "pesquisa": "Pesquisa",
            "historico": "Dashboard historico",
            "scanner_intradiario": "Scanner intradiario",
            "paper_ao_vivo": "Paper trading ao vivo",
            "analise_assistida": "Analise assistida",
        }[self.value]


class TempoRealIndisponivelError(DataError):
    """Pediram dado de tempo real e nao ha provedor capaz. Nunca cai para atrasado."""


@dataclass(frozen=True)
class Leitura:
    """O que o servico devolve: dado + de onde veio + se da para confiar."""

    serie: Series
    fonte: str
    status: StatusDados
    finalidade: Finalidade
    qualidade: Qualidade
    lida_em: datetime

    @property
    def utilizavel(self) -> bool:
        """Serve para a finalidade pedida?"""
        if not self.qualidade.valida or not self.status.tem_dado:
            return False
        if self.finalidade.exige_tempo_real:
            return self.status.serve_para_tempo_real
        return True

    @property
    def aviso(self) -> str:
        if not self.qualidade.valida:
            return f"DADOS INVALIDOS: {self.qualidade.bloqueios[0].mensagem}"
        return self.status.aviso

    def para_dict(self) -> dict:
        return {
            "symbol": self.serie.symbol, "timeframe": self.serie.timeframe,
            "candles": len(self.serie), "fonte": self.fonte,
            "status": self.status.value, "finalidade": self.finalidade.value,
            "utilizavel": self.utilizavel, "aviso": self.aviso,
            "qualidade": self.qualidade.para_dict(),
            "lida_em": self.lida_em.isoformat(),
        }


class MarketDataService:
    """A porta unica de dados de mercado do Cashinho."""

    def __init__(
        self,
        historico: Optional[Provider] = None,
        tempo_real: Optional[Provider] = None,
        validador: Optional[ValidadorDeQualidade] = None,
        relogio: Optional[Callable[[], datetime]] = None,
        log=None,
    ):
        from ..core.log import RegistradorNulo

        self.historico = historico
        self.tempo_real = tempo_real
        self.validador = validador or ValidadorDeQualidade()
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self.log = log or RegistradorNulo()

    # ------------------------------------------------------------------
    @property
    def tem_tempo_real(self) -> bool:
        return self.tempo_real is not None

    def provedor(self, finalidade: Finalidade) -> Provider:
        """O provedor daquela finalidade - ou o erro que explica a falta."""
        if finalidade.exige_tempo_real:
            if self.tempo_real is None:
                raise TempoRealIndisponivelError(
                    f"{finalidade.rotulo} exige provedor de tempo real, e nenhum esta "
                    "configurado. O Cashinho nao usa dado historico no lugar: "
                    "seria apresentar preco velho como mercado")
            return self.tempo_real
        if self.historico is None:
            raise DataError("nenhum provedor historico configurado")
        return self.historico

    def capacidades(self, finalidade: Finalidade) -> Capacidades:
        p = self.provedor(finalidade)
        return getattr(p, "capacidades", Capacidades())

    # ------------------------------------------------------------------
    def candles(self, symbol: str, timeframe: str, dias: int = 5,
                finalidade: Finalidade = Finalidade.HISTORICO) -> Leitura:
        """Candles normalizados, com origem, estado e qualidade juntos."""
        provedor = self.provedor(finalidade)
        nome = getattr(provedor, "nome", "?")

        if finalidade.exige_tempo_real:
            self._exigir_capacidade_intradiaria(provedor, nome, timeframe)

        try:
            serie = provedor.candles(symbol, timeframe, dias)
        except DataError as e:
            self.log.erro("market_data", f"{nome}: {symbol} {timeframe}: {e}",
                          symbol=symbol, provedor=nome)
            raise

        agora = self._relogio()
        qualidade = self.validador.validar(serie)
        status = self._status(provedor, serie, timeframe, agora)
        leitura = Leitura(serie, nome, status, finalidade, qualidade, agora)

        if not qualidade.valida:
            self.log.erro("market_data", f"{nome}: {symbol} reprovado na qualidade",
                          problemas=[p.chave for p in qualidade.bloqueios])
        elif not leitura.utilizavel:
            self.log.aviso("market_data",
                           f"{nome}: {symbol} {status.value} - {status.aviso}")
        return leitura

    def cotacao(self, symbol: str,
                finalidade: Finalidade = Finalidade.HISTORICO) -> Cotacao:
        provedor = self.provedor(finalidade)
        if not hasattr(provedor, "cotacao"):
            raise CapacidadeAusenteError(
                f"o provedor '{getattr(provedor, 'nome', '?')}' nao entrega cotacao")
        cot = provedor.cotacao(symbol)
        if finalidade.exige_tempo_real and not cot.serve_para_tempo_real:
            raise TempoRealIndisponivelError(
                f"{finalidade.rotulo} pediu cotacao de {symbol}, mas o dado veio "
                f"{cot.status.value} ({cot.idade_legivel}). {cot.status.aviso}")
        return cot

    # ------------------------------------------------------------------
    def _exigir_capacidade_intradiaria(self, provedor, nome: str, timeframe: str) -> None:
        cap = getattr(provedor, "capacidades", Capacidades())
        if timeframe == "1m" and not cap.intradiario_1m:
            raise CapacidadeAusenteError(
                f"'{nome}' nao declara intradiario de 1m - exigido para esta finalidade")
        if not cap.serve_para_day_trade:
            raise CapacidadeAusenteError(
                f"'{nome}' nao serve para day trade: cotacao em tempo real="
                f"{cap.cotacao_em_tempo_real}, 1m={cap.intradiario_1m}, "
                f"atraso declarado={cap.atraso_tipico_s}")

    def _status(self, provedor, serie: Series, timeframe: str,
                agora: datetime) -> StatusDados:
        if not len(serie):
            return StatusDados.OFFLINE
        classificar = getattr(provedor, "classificar", None)
        if classificar is None:
            return StatusDados.DEGRADED  # provedor antigo, sem estado declarado
        return classificar(serie.candles[-1].ts, timeframe, agora)

    # ------------------------------------------------------------------
    def para_dict(self) -> dict:
        def descreve(p):
            if p is None:
                return None
            return {"nome": getattr(p, "nome", "?"),
                    "capacidades": getattr(p, "capacidades", Capacidades()).para_dict()}

        return {
            "historico": descreve(self.historico),
            "tempo_real": descreve(self.tempo_real),
            "tem_tempo_real": self.tem_tempo_real,
            "analise_em_tempo_real": ("DISPONIVEL" if self.tem_tempo_real
                                      else "INDISPONIVEL"),
        }
