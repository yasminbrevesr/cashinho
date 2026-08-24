"""``MarketDataProvider``: o contrato unico que o resto do Cashinho enxerga.

Estrategia, indicador, scanner, backtest e Risk Manager **nao sabem** de onde
o dado vem. Eles pedem candles ou cotacao e recebem sempre o mesmo formato -
com a origem, o estado e a idade grudados.

Esta classe estende o ``Provider`` que ja existia em vez de criar uma
hierarquia paralela: os provedores atuais (sintetico, CSV, Yahoo) continuam
valendo, e ganham capacidades declaradas.

Nomes: o projeto inteiro e' em portugues, entao os metodos sao ``candles``,
``cotacao``, ``timeframes``, ``simbolos`` e ``status``. Os nomes em ingles do
enunciado (``get_candles``, ``get_quote``, ...) existem como **apelidos** na
classe base, para quem preferir chama-los assim.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from ..models import BRT, Series
from .base import DataError, Provider
from .cotacao import Cotacao
from .status import Capacidades, StatusDados, exigir

# quanto tempo sem candle novo derruba o dado, por timeframe. Nao ha limite
# universal: candle diario de 40 min atras esta em dia, candle de 1m nao.
# O multiplicador e' sobre a duracao do proprio timeframe.
FATOR_STALE = 3.0
FOLGA_MINIMA_S = 90.0
# margem sobre o atraso declarado antes de considerar a cotacao parada
MARGEM_COTACAO_S = 300.0


def limite_de_stale(timeframe: str, fator: float = FATOR_STALE) -> float:
    """Segundos sem dado novo a partir dos quais o candle esta parado.

    No intradiario o relogio de parede serve. No diario, nao: na segunda-feira
    o ultimo candio fechado e' o de sexta, e cobrar dele as horas de fim de
    semana acusaria parada toda semana. Por isso o timeframe de sessao inteira
    conta em **dias de calendario** com folga para feriado prolongado.
    """
    from ..core.mtf.timeframes import parse_timeframe

    try:
        tf = parse_timeframe(timeframe)
    except Exception:
        return max(5 * 60 * fator, FOLGA_MINIMA_S)

    if tf.sessao_inteira:
        # 'fator' candles diarios podem cair sobre um feriadao: 4 dias de
        # calendario por candio cobrem sexta -> terca sem alarme falso
        return fator * 4 * 24 * 3600
    return max(tf.minutos * 60 * fator, FOLGA_MINIMA_S)


class MarketDataProvider(Provider):
    """Fonte de dados de mercado, com capacidades e estado declarados."""

    nome: str = "market-data"
    # todo provedor declara o que sabe fazer. O padrao e' "nao sei nada":
    # capacidade nao declarada e' capacidade que nao existe
    capacidades: Capacidades = Capacidades()

    # -- o que toda fonte precisa responder ------------------------------
    @abstractmethod
    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        """Serie de candles normalizada. Levanta ``DataError`` quando nao da."""

    def cotacao(self, symbol: str) -> Cotacao:
        """Cotacao atual - que pode vir atrasada, e o status dira isso.

        Provedor que nao declara entregar cotacao recusa aqui, em vez de
        improvisar uma cotacao a partir do ultimo candle.
        """
        exigir(self.capacidades, self.nome, cotacao=True)
        raise NotImplementedError(
            f"{self.nome} declara entregar cotacao mas nao implementou cotacao()")

    def timeframes(self) -> tuple[str, ...]:
        """Os timeframes que este provedor declara suportar."""
        return self.capacidades.timeframes

    def simbolos(self) -> tuple[str, ...]:
        """Ativos conhecidos. Vazio = o provedor nao lista (nao que nao tenha)."""
        return ()

    def status(self, symbol: str = "", timeframe: str = "1d") -> StatusDados:
        """Estado do provedor agora. O padrao e' medir pelo ultimo candle."""
        try:
            serie = self.candles(symbol or "PETR4", timeframe, 1)
        except DataError:
            return StatusDados.OFFLINE
        if not len(serie):
            return StatusDados.OFFLINE
        return self.classificar(serie.candles[-1].ts, timeframe)

    # -- utilitario compartilhado -----------------------------------------
    def classificar(self, ts_do_dado: datetime, timeframe: str,
                    agora: Optional[datetime] = None) -> StatusDados:
        """Traduz idade do dado em estado, respeitando o atraso declarado.

        Um provedor que **declara** atraso nunca sai ONLINE: o dado dele e'
        DELAYED por natureza, e so vira STALE quando para de atualizar mesmo,
        alem do atraso que ele mesmo prometeu.
        """
        instante = agora or datetime.now(BRT)
        if ts_do_dado.tzinfo is None:
            raise ValueError("timestamp sem fuso: o Cashinho nao aceita horario ingenuo")
        idade = (instante - ts_do_dado).total_seconds()

        atraso = self.capacidades.atraso_tipico_s
        limite = limite_de_stale(timeframe)
        if atraso is not None and atraso > 0:
            # o atraso prometido entra no orcamento antes de chamar de parado
            if idade > atraso + limite:
                return StatusDados.STALE
            return StatusDados.DELAYED
        if idade > limite:
            return StatusDados.STALE
        return StatusDados.ONLINE

    def classificar_cotacao(self, momento: datetime,
                            agora: Optional[datetime] = None) -> StatusDados:
        """Estado de uma **cotacao** - regua diferente da do candle.

        Um candle diario de ontem esta em dia; uma cotacao de ontem, nao. O
        orcamento aqui e' o atraso que o proprio provedor declarou, mais uma
        margem. Alem disso, a fonte parou de atualizar.
        """
        instante = agora or datetime.now(BRT)
        if momento.tzinfo is None:
            raise ValueError("timestamp sem fuso: o Cashinho nao aceita horario ingenuo")
        idade = (instante - momento).total_seconds()

        atraso = self.capacidades.atraso_tipico_s
        if atraso is None:
            # sem atraso declarado nao ha o que considerar normal alem do agora
            return StatusDados.ONLINE if idade <= MARGEM_COTACAO_S else StatusDados.STALE
        if idade > atraso + max(atraso, MARGEM_COTACAO_S):
            return StatusDados.STALE
        return StatusDados.ONLINE if atraso <= 60 else StatusDados.DELAYED

    # -- apelidos em ingles, para quem preferir ----------------------------
    def get_candles(self, symbol: str, timeframe: str, limit: Optional[int] = None,
                    **extra) -> Series:
        serie = self.candles(symbol, timeframe, extra.get("dias", 5))
        return serie.tail(limit) if limit else serie

    def get_quote(self, symbol: str) -> Cotacao:
        return self.cotacao(symbol)

    def get_available_timeframes(self) -> tuple[str, ...]:
        return self.timeframes()

    def get_symbols(self) -> tuple[str, ...]:
        return self.simbolos()

    def get_status(self, symbol: str = "", timeframe: str = "1d") -> StatusDados:
        return self.status(symbol, timeframe)

    # -- descricao ---------------------------------------------------------
    def para_dict(self) -> dict:
        return {"provedor": self.nome, "capacidades": self.capacidades.para_dict()}
