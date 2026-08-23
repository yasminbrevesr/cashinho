"""De onde o contexto tira numero - e o que fazer quando nao tira.

Toda fonte responde duas perguntas: **quais instrumentos ela atende** e **qual
serie ela devolve**. O que ela nao pode fazer e' devolver um numero que nao
veio de lugar nenhum: falhar levanta ``DataError`` e o instrumento entra no
contexto como indisponivel, que e' informacao verdadeira.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Sequence

from ...data.base import DataError, Provider
from ...models import BRT, Candle, Series
from .instrumentos import Instrumento


class FonteDeContexto(ABC):
    """Contrato de uma fonte do contexto."""

    nome: str = "fonte"
    simulada: bool = False
    descricao: str = ""

    @abstractmethod
    def atende(self, instrumento: Instrumento) -> bool:
        """Esta fonte sabe buscar este instrumento?"""

    @abstractmethod
    def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
        """Serie do instrumento. Levanta ``DataError`` quando nao der."""


class FonteProvider(FonteDeContexto):
    """Adapta qualquer :class:`Provider` da camada de dados a uma fonte.

    O ticker sai do catalogo (``instrumento.tickers[nome_da_fonte]``): nenhum
    ticker e' montado por adivinhacao aqui.
    """

    def __init__(self, provider: Provider, nome: Optional[str] = None,
                 simulada: bool = False):
        self.provider = provider
        self.nome = nome or provider.nome
        self.simulada = simulada

    def atende(self, instrumento: Instrumento) -> bool:
        return instrumento.ticker(self.nome) is not None

    def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
        ticker = instrumento.ticker(self.nome)
        if ticker is None:
            raise DataError(f"{self.nome} nao atende {instrumento.chave}")
        return self.provider.candles(ticker, timeframe, dias)


def fonte_yahoo(**kwargs) -> FonteProvider:
    """Yahoo Finance: indices, cambio e futuros de commodity.

    Cotacao com atraso (~15 min no intradiario). O contexto trata isso como
    ambiente, nao como book - e a defasagem aparece na qualidade dos dados.
    """
    from ...data.yahoo import YahooProvider

    return FonteProvider(YahooProvider(**kwargs), nome="yahoo")


class FonteBCB(FonteDeContexto):
    """Series diarias do Banco Central (SGS) - a fonte de juros.

    E' API publica e oficial, e a serie e' **diaria**: o valor muda uma vez
    por dia. Serve para dizer em que patamar o juro esta, nao para reagir
    intradiario.
    """

    nome = "bcb"
    descricao = "Banco Central do Brasil - Sistema Gerenciador de Series (SGS)"
    URL = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/"
           "{n}?formato=json")

    def __init__(self, timeout: int = 10, abrir=None):
        self.timeout = timeout
        self._abrir = abrir  # injetavel nos testes; None = urllib

    def atende(self, instrumento: Instrumento) -> bool:
        return instrumento.ticker(self.nome) is not None

    def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
        codigo = instrumento.ticker(self.nome)
        if codigo is None:
            raise DataError(f"bcb nao atende {instrumento.chave}")

        bruto = self._buscar(codigo, max(dias, 2))
        candles: list[Candle] = []
        for linha in bruto:
            try:
                dia = datetime.strptime(linha["data"], "%d/%m/%Y").replace(
                    hour=10, minute=0, tzinfo=BRT)
                valor = float(str(linha["valor"]).replace(",", "."))
                candles.append(Candle(dia, valor, valor, valor, valor, 0.0))
            except (KeyError, TypeError, ValueError):
                continue  # linha estranha e' descartada, nunca "corrigida"

        if not candles:
            raise DataError(f"SGS {codigo}: resposta sem valores utilizaveis")
        return Series(instrumento.chave, "1d", candles)

    # ------------------------------------------------------------------
    def _buscar(self, codigo: str, n: int) -> list[dict]:
        url = self.URL.format(serie=codigo, n=n)
        try:
            if self._abrir is not None:
                texto = self._abrir(url)
            else:  # pragma: no cover - depende da rede
                from urllib.request import urlopen

                with urlopen(url, timeout=self.timeout) as r:
                    texto = r.read().decode("utf-8")
        except Exception as e:
            raise DataError(f"falha ao consultar o SGS {codigo}: {e}") from e

        try:
            dados = json.loads(texto)
        except ValueError as e:
            raise DataError(f"SGS {codigo}: resposta nao e' JSON") from e
        if not isinstance(dados, list):
            raise DataError(f"SGS {codigo}: formato inesperado")
        return dados


class FonteComposta(FonteDeContexto):
    """Varias fontes em ordem: a primeira que atender responde."""

    nome = "composta"

    def __init__(self, fontes: Sequence[FonteDeContexto]):
        if not fontes:
            raise ValueError("informe ao menos uma fonte")
        self.fontes = tuple(fontes)

    @property
    def simulada(self) -> bool:  # type: ignore[override]
        return any(f.simulada for f in self.fontes)

    def fonte_de(self, instrumento: Instrumento) -> Optional[FonteDeContexto]:
        for f in self.fontes:
            if f.atende(instrumento):
                return f
        return None

    def atende(self, instrumento: Instrumento) -> bool:
        return self.fonte_de(instrumento) is not None

    def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
        erros = []
        for f in self.fontes:
            if not f.atende(instrumento):
                continue
            try:
                return f.serie(instrumento, timeframe, dias)
            except DataError as e:
                erros.append(f"{f.nome}: {e}")
        if erros:
            raise DataError("; ".join(erros))
        raise DataError(f"nenhuma fonte atende {instrumento.chave}")


def fonte_demo(semente: int = 7) -> FonteProvider:
    """Fonte de demonstracao - **nao sao cotacoes reais**.

    Existe para a tela e os testes rodarem sem rede. Tudo que sai daqui chega
    ao contexto marcado como SIMULADA, e contexto simulado nao pesa em decisao
    nenhuma (ver ``NivelDeQualidade.confiavel``).
    """
    from ...data.synthetic import SyntheticProvider

    class _Demo(SyntheticProvider):
        nome = "demo"

    provider = _Demo(semente=semente)
    # o catalogo nao declara tickers de demo: a fonte de demonstracao atende
    # qualquer instrumento QUE TENHA alguma fonte real declarada, e nenhum dos
    # que estao marcados como sem fonte confiavel
    class _FonteDemo(FonteProvider):
        def atende(self, instrumento: Instrumento) -> bool:
            return instrumento.tem_fonte

        def serie(self, instrumento: Instrumento, timeframe: str, dias: int) -> Series:
            return self.provider.candles(instrumento.chave.upper(), timeframe, dias)

    return _FonteDemo(provider, nome="demo", simulada=True)
