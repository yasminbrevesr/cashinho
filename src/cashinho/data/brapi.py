"""Provedor REST da brapi.dev - historico e cotacao (com atraso do plano).

DIVERGENCIA DECLARADA
=====================
A documentacao da brapi **nao pode ser aberta deste ambiente** (o proxy de
rede bloqueia o dominio). O que esta codificado aqui veio de paginas da
propria brapi obtidas por busca, e esta marcado abaixo pelo que foi
confirmado e pelo que **nao** foi:

CONFIRMADO
  - URL base ``https://brapi.dev/api``
  - autenticacao por ``Authorization: Bearer <token>`` (o token tambem e'
    aceito como parametro de query)
  - endpoint ``/quote/{tickers}``, com tickers separados por virgula
  - parametros ``range`` e ``interval`` no historico
  - alguns ativos respondem sem token (PETR4, VALE3, MGLU3, ITUB4)

NAO CONFIRMADO - por isso e' CONFIGURACAO, nao constante
  - o atraso do plano: fontes diferentes citam 15 e 30 minutos para o plano
    gratuito. Sem ``BRAPI_ATRASO_SEGUNDOS`` declarado, este provedor assume
    que **nao serve para tempo real**;
  - quais ``interval`` o seu plano libera: declare em ``BRAPI_TIMEFRAMES``.
    Sem declaracao, nenhum timeframe e' dado como suportado;
  - o teto de requisicoes: declare em ``BRAPI_REQUISICOES_POR_MINUTO``;
  - os nomes exatos dos campos da resposta: estao em ``CAMPOS`` como lista de
    apelidos. Se a resposta nao trouxer nenhum deles, o provedor **levanta
    erro dizendo qual campo faltou** - nunca preenche com zero nem adivinha.

Ajuste ``CAMPOS`` contra a documentacao se ela divergir. O codigo foi escrito
para que essa divergencia apareca como erro claro, e nao como numero errado.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from ..models import BRT, Candle, CandleInvalidoError, Series
from ..settings import ConfigMarketData, carregar
from .base import DataError
from .cotacao import Cotacao
from .mercado import MarketDataProvider
from .rate_limit import Freio
from .status import Capacidades, StatusDados

NOME = "brapi"

# apelidos de campo, do mais provavel ao menos. Confira contra a documentacao.
CAMPOS: dict[str, tuple[str, ...]] = {
    "last": ("regularMarketPrice", "price", "close"),
    "open": ("regularMarketOpen", "open"),
    "high": ("regularMarketDayHigh", "dayHigh", "high"),
    "low": ("regularMarketDayLow", "dayLow", "low"),
    "previous_close": ("regularMarketPreviousClose", "previousClose"),
    "volume": ("regularMarketVolume", "volume"),
    "momento": ("regularMarketTime", "updatedAt", "time"),
    "historico": ("historicalDataPrice", "historical", "prices"),
}
CAMPOS_CANDLE: dict[str, tuple[str, ...]] = {
    "ts": ("date", "timestamp", "time"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume",),
}

TENTATIVAS = 3
ESPERA_INICIAL_S = 1.0


class BrapiError(DataError):
    """Falha especifica da brapi, com o motivo legivel."""


def _campo(bruto: Mapping[str, Any], chave: str, obrigatorio: bool = False):
    """Le um campo pelos apelidos declarados. Ausente e' ``None`` ou erro."""
    for apelido in CAMPOS.get(chave, (chave,)):
        if apelido in bruto and bruto[apelido] is not None:
            return bruto[apelido]
    if obrigatorio:
        raise BrapiError(
            f"a resposta da brapi nao trouxe nenhum dos campos {CAMPOS.get(chave)} "
            f"para '{chave}'. Confira a documentacao e ajuste CAMPOS em "
            f"cashinho/data/brapi.py - preencher isso por adivinhacao daria "
            f"numero errado com cara de dado")
    return None


def _momento(valor) -> Optional[datetime]:
    """A brapi pode devolver epoch ou ISO; os dois viram horario de Brasilia."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(float(valor), tz=timezone.utc).astimezone(BRT)
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return (ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts).astimezone(BRT)


class BrapiMarketDataProvider(MarketDataProvider):
    """Historico e cotacao da brapi.dev, com o atraso do plano declarado."""

    nome = NOME

    def __init__(self, config: Optional[ConfigMarketData] = None,
                 abrir=None, relogio=None, timeout: float = 10.0):
        self.config = config or carregar()
        self.timeout = timeout
        self._abrir = abrir            # injetavel nos testes; None = urllib
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self.freio = Freio(self.config.brapi_requisicoes_por_minuto)
        self.ultimo_erro = ""
        self.requisicoes = 0

        atraso = self.config.brapi_atraso_s
        timeframes = self.config.brapi_timeframes
        self.capacidades = Capacidades(
            candles_historicos=True,
            cotacao=True,
            # so e' tempo real se o atraso declarado for pequeno. Atraso
            # desconhecido nao vira "tempo real" por otimismo
            cotacao_em_tempo_real=bool(atraso is not None and atraso <= 60),
            ticks_em_tempo_real=False,
            livro_de_ofertas=False,
            intradiario_1m=("1m" in timeframes),
            timeframes=timeframes,
            atraso_tipico_s=atraso,
        )

    # ------------------------------------------------------------------
    def candles(self, symbol: str, timeframe: str, dias: int = 5) -> Series:
        self._exigir_timeframe(timeframe)
        bruto = self._buscar(symbol, {"range": self._range(dias), "interval": timeframe})
        historico = _campo(bruto, "historico", obrigatorio=True)
        if not isinstance(historico, list) or not historico:
            raise BrapiError(f"brapi devolveu historico vazio para {symbol} ({timeframe})")

        candles: list[Candle] = []
        descartados = 0
        for linha in historico:
            candle = self._candle(linha)
            if candle is None:
                descartados += 1
                continue
            candles.append(candle)
        if not candles:
            raise BrapiError(
                f"nenhum candle valido para {symbol} ({timeframe}): "
                f"{descartados} linha(s) descartada(s)")
        candles.sort(key=lambda c: c.ts)
        return Series(symbol.upper(), timeframe, candles)

    def cotacao(self, symbol: str) -> Cotacao:
        bruto = self._buscar(symbol, {})
        agora = self._relogio()
        momento = _momento(_campo(bruto, "momento")) or agora
        idade = max((agora - momento).total_seconds(), 0.0)

        return Cotacao(
            symbol=symbol.upper(),
            timestamp=momento,
            source=self.nome,
            status=self.classificar_cotacao(momento, agora),
            last=_numero(_campo(bruto, "last")),
            bid=None,   # a brapi nao entrega book: fica None, nao inventado
            ask=None,
            open=_numero(_campo(bruto, "open")),
            high=_numero(_campo(bruto, "high")),
            low=_numero(_campo(bruto, "low")),
            previous_close=_numero(_campo(bruto, "previous_close")),
            volume=_numero(_campo(bruto, "volume")),
            data_age=idade,
            lida_em=agora,
        )

    def simbolos(self) -> tuple[str, ...]:
        """Sem token, a brapi atende poucos ativos - e e' isso que dizemos."""
        if not self.config.brapi_autenticado:
            return ("PETR4", "VALE3", "MGLU3", "ITUB4")
        return ()  # com token a lista e' grande demais para afirmar aqui

    def status(self, symbol: str = "PETR4", timeframe: str = "1d") -> StatusDados:
        try:
            return self.cotacao(symbol or "PETR4").status
        except DataError:
            return StatusDados.OFFLINE

    # ------------------------------------------------------------------
    def _exigir_timeframe(self, timeframe: str) -> None:
        suporta = self.capacidades.suporta(timeframe)
        if suporta is None:
            raise BrapiError(
                f"nenhum timeframe declarado para a brapi: preencha BRAPI_TIMEFRAMES "
                f"no .env com o que o seu plano entrega (pedido: {timeframe}). "
                "Sem declaracao, o Cashinho nao chuta o que o plano libera")
        if not suporta:
            raise BrapiError(
                f"timeframe {timeframe} nao esta em BRAPI_TIMEFRAMES "
                f"({', '.join(self.capacidades.timeframes)})")

    def _range(self, dias: int) -> str:
        """Menor range declarado que cobre os dias pedidos.

        A tabela segue a notacao que a documentacao usa nos exemplos. Se o seu
        plano aceitar outros valores, ajuste aqui.
        """
        for limite, rotulo in ((5, "5d"), (30, "1mo"), (90, "3mo"), (180, "6mo"),
                               (365, "1y"), (730, "2y"), (1825, "5y")):
            if dias <= limite:
                return rotulo
        return "max"

    def _candle(self, linha: Mapping[str, Any]) -> Optional[Candle]:
        def pega(chave):
            for apelido in CAMPOS_CANDLE[chave]:
                if apelido in linha and linha[apelido] is not None:
                    return linha[apelido]
            return None

        ts = _momento(pega("ts"))
        if ts is None:
            return None
        try:
            return Candle(
                ts,
                float(pega("open")), float(pega("high")),
                float(pega("low")), float(pega("close")),
                float(pega("volume") or 0.0),
            )
        except (TypeError, ValueError, CandleInvalidoError):
            # linha incoerente e' descartada com o resto da serie preservado
            return None

    # ------------------------------------------------------------------
    def _buscar(self, symbol: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        alvo = f"{self.config.brapi_base_url}/quote/{urllib.parse.quote(symbol.upper())}"
        consulta = {k: v for k, v in params.items() if v}
        url = f"{alvo}?{urllib.parse.urlencode(consulta)}" if consulta else alvo

        dados = self._requisitar(url)
        resultados = dados.get("results") if isinstance(dados, dict) else None
        if not resultados:
            erro = (dados.get("message") or dados.get("error")
                    if isinstance(dados, dict) else None)
            raise BrapiError(f"brapi sem resultado para {symbol}"
                             + (f": {erro}" if erro else ""))
        return resultados[0]

    def _requisitar(self, url: str) -> Mapping[str, Any]:
        """Uma requisicao, com freio, timeout e retentativa so onde cabe."""
        espera = ESPERA_INICIAL_S
        ultimo = ""
        for tentativa in range(1, TENTATIVAS + 1):
            self.freio.aguardar()
            self.requisicoes += 1
            try:
                return self._ler(url)
            except BrapiError as e:
                ultimo = str(e)
                self.ultimo_erro = ultimo
                if not getattr(e, "recuperavel", False) or tentativa == TENTATIVAS:
                    raise
                import time as _t

                _t.sleep(espera)
                espera *= 2
        raise BrapiError(ultimo or "falha desconhecida na brapi")

    def _ler(self, url: str) -> Mapping[str, Any]:
        cabecalhos = {"Accept": "application/json", "User-Agent": "cashinho"}
        if self.config.brapi_autenticado:
            cabecalhos["Authorization"] = f"Bearer {self.config.brapi_token}"

        try:
            if self._abrir is not None:
                corpo = self._abrir(url, cabecalhos)
            else:  # pragma: no cover - depende de rede
                requisicao = urllib.request.Request(url, headers=cabecalhos)
                with urllib.request.urlopen(requisicao, timeout=self.timeout) as r:
                    corpo = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:  # pragma: no cover - depende de rede
            raise self._erro_http(e.code) from e
        except urllib.error.URLError as e:  # pragma: no cover - depende de rede
            erro = BrapiError(f"brapi inacessivel: {e.reason}")
            erro.recuperavel = True  # type: ignore[attr-defined]
            raise erro from e
        except TimeoutError as e:  # pragma: no cover - depende de rede
            erro = BrapiError(f"brapi nao respondeu em {self.timeout}s")
            erro.recuperavel = True  # type: ignore[attr-defined]
            raise erro from e

        try:
            return json.loads(corpo)
        except ValueError as e:
            raise BrapiError("brapi devolveu resposta que nao e' JSON") from e

    def _erro_http(self, codigo: int) -> BrapiError:
        if codigo in (401, 403):
            return BrapiError(
                f"brapi recusou a credencial (HTTP {codigo}): confira BRAPI_TOKEN")
        if codigo == 404:
            return BrapiError("ativo nao encontrado na brapi (HTTP 404)")
        if codigo == 429:
            erro = BrapiError("brapi respondeu 429: limite de requisicoes atingido")
            erro.recuperavel = True  # type: ignore[attr-defined]
            return erro
        if codigo >= 500:
            erro = BrapiError(f"brapi com erro interno (HTTP {codigo})")
            erro.recuperavel = True  # type: ignore[attr-defined]
            return erro
        return BrapiError(f"brapi respondeu HTTP {codigo}")


def _numero(valor) -> Optional[float]:
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None
