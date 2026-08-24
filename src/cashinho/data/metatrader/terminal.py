"""O unico arquivo do Cashinho que importa ``MetaTrader5``.

Tudo o que e' especifico do MT5 - constantes de timeframe, tipos de tick,
formato dos retornos - fica atras desta fronteira. O dominio nunca ve
``MetaTrader5``: ha teste que varre o projeto para garantir isso.

A biblioteca so existe no Windows. Aqui ela e' importada **dentro** dos
metodos, e a ausencia dela vira estado descrito (``METATRADER NAO
DISPONIVEL``), nunca ``ImportError`` no meio de um backtest em Linux ou na CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

# tipos de tick que o MT5 expoe. Ficam aqui como nome, e viram constante da
# biblioteca so na hora da chamada
TICKS_INFO = "COPY_TICKS_INFO"      # bid e ask
TICKS_TRADE = "COPY_TICKS_TRADE"    # last e volume

# mapeamento dos timeframes do Cashinho para os do MT5
TIMEFRAMES: dict[str, str] = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "60m": "TIMEFRAME_H1",
    "1d": "TIMEFRAME_D1",
}


class MT5Indisponivel(RuntimeError):
    """A biblioteca MetaTrader5 nao esta instalada ou nao roda aqui."""


class MT5Error(RuntimeError):
    """Falha do terminal, com o codigo e a mensagem que ele deu."""


@dataclass(frozen=True)
class InfoTerminal:
    """O que da para dizer do terminal **sem** expor dado da conta."""

    conectado: bool
    empresa: str = ""
    servidor: str = ""
    caminho: str = ""
    versao: str = ""
    motivo: str = ""

    def para_dict(self) -> dict:
        # nao ha login, saldo nem patrimonio aqui, e nao deve haver:
        # System Health mostra este dicionario
        return {
            "conectado": self.conectado, "empresa": self.empresa,
            "servidor": self.servidor, "versao": self.versao,
            "motivo": self.motivo,
        }


class TerminalMT5:
    """Adaptador fino sobre a biblioteca MetaTrader5.

    Cada metodo devolve estrutura simples (dict/tupla), nunca objeto do MT5:
    e' o que permite trocar a biblioteca por um dublê nos testes sem nenhum
    ``if teste`` no codigo de producao.
    """

    def __init__(self, caminho_terminal: str = "", mt5: Any = None):
        self.caminho_terminal = caminho_terminal
        self._mt5 = mt5
        self._iniciado = False

    # ------------------------------------------------------------------
    @property
    def biblioteca(self) -> Any:
        """A biblioteca, ou o erro explicando que ela nao esta aqui."""
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as e:
            raise MT5Indisponivel(
                "METATRADER NAO DISPONIVEL: a biblioteca MetaTrader5 nao esta "
                "instalada (ela so existe no Windows). Instale com "
                "'pip install MetaTrader5' na maquina com o terminal da Genial"
            ) from e
        self._mt5 = mt5
        return mt5

    @property
    def disponivel(self) -> bool:
        try:
            self.biblioteca
        except MT5Indisponivel:
            return False
        return True

    # ------------------------------------------------------------------
    def conectar(self) -> InfoTerminal:
        """Liga no terminal **ja aberto e autenticado**.

        Nao recebe login nem senha de proposito: o Cashinho nao guarda
        credencial da Genial. Quem autentica e' voce, no terminal.
        """
        try:
            mt5 = self.biblioteca
        except MT5Indisponivel as e:
            return InfoTerminal(False, motivo=str(e))

        ok = (mt5.initialize(self.caminho_terminal) if self.caminho_terminal
              else mt5.initialize())
        if not ok:
            return InfoTerminal(False, motivo=self._ultimo_erro())

        self._iniciado = True
        return self._descrever()

    def _descrever(self) -> InfoTerminal:
        mt5 = self.biblioteca
        info = mt5.terminal_info()
        if info is None:
            return InfoTerminal(False, motivo="terminal_info() nao respondeu")

        conta = mt5.account_info()
        # SO o nome do servidor - nunca login, saldo ou patrimonio
        servidor = getattr(conta, "server", "") if conta is not None else ""
        return InfoTerminal(
            conectado=bool(getattr(info, "connected", False)),
            empresa=str(getattr(info, "company", "") or ""),
            servidor=str(servidor or ""),
            caminho=str(getattr(info, "path", "") or ""),
            versao=str(getattr(mt5, "__version__", "") or ""),
        )

    def desconectar(self) -> None:
        if self._iniciado and self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
            self._iniciado = False

    # ------------------------------------------------------------------
    def simbolos(self) -> tuple[str, ...]:
        mt5 = self.biblioteca
        achados = mt5.symbols_get()
        if not achados:
            return ()
        return tuple(str(getattr(s, "name", "")) for s in achados if getattr(s, "name", ""))

    def info_simbolo(self, symbol: str) -> Optional[dict]:
        mt5 = self.biblioteca
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            "name": str(getattr(info, "name", symbol)),
            "visible": bool(getattr(info, "visible", False)),
            "digits": int(getattr(info, "digits", 2) or 2),
            "trade_mode": getattr(info, "trade_mode", None),
        }

    def selecionar(self, symbol: str) -> bool:
        """Poe o ativo na Observacao do Mercado - sem isso nao vem tick."""
        return bool(self.biblioteca.symbol_select(symbol, True))

    # ------------------------------------------------------------------
    def ticks(self, symbol: str, desde: datetime, quantidade: int,
              tipo: str) -> tuple[dict, ...]:
        """Ticks do tipo pedido, ja como dicionarios simples."""
        mt5 = self.biblioteca
        constante = getattr(mt5, tipo, None)
        if constante is None:
            raise MT5Error(f"a biblioteca MetaTrader5 nao expoe {tipo}")

        bruto = mt5.copy_ticks_from(symbol, desde, quantidade, constante)
        if bruto is None:
            raise MT5Error(f"copy_ticks_from({symbol}, {tipo}) falhou: "
                           f"{self._ultimo_erro()}")
        return tuple(_como_dict(t) for t in bruto)

    def candles(self, symbol: str, timeframe: str, quantidade: int) -> tuple[dict, ...]:
        """Candles a partir da posicao 0 - inclusive o que esta em formacao."""
        mt5 = self.biblioteca
        nome = TIMEFRAMES.get(timeframe)
        if nome is None:
            raise MT5Error(f"timeframe sem correspondencia no MT5: {timeframe}")
        constante = getattr(mt5, nome, None)
        if constante is None:
            raise MT5Error(f"a biblioteca MetaTrader5 nao expoe {nome}")

        bruto = mt5.copy_rates_from_pos(symbol, constante, 0, quantidade)
        if bruto is None:
            raise MT5Error(f"copy_rates_from_pos({symbol}, {timeframe}) falhou: "
                           f"{self._ultimo_erro()}")
        return tuple(_como_dict(r) for r in bruto)

    # ------------------------------------------------------------------
    def livro_disponivel(self, symbol: str) -> bool:
        """Livro de ofertas e' capacidade **detectada**, nunca presumida."""
        mt5 = self.biblioteca
        if not hasattr(mt5, "market_book_add"):
            return False
        try:
            if not mt5.market_book_add(symbol):
                return False
        except Exception:
            return False
        try:
            return mt5.market_book_get(symbol) is not None
        except Exception:
            return False
        finally:
            try:
                mt5.market_book_release(symbol)
            except Exception:
                pass

    def _ultimo_erro(self) -> str:
        try:
            codigo, mensagem = self.biblioteca.last_error()
            return f"MT5 [{codigo}] {mensagem}"
        except Exception:
            return "erro desconhecido do MT5"


def _como_dict(registro: Any) -> dict:
    """Converte a linha do numpy/named tuple do MT5 em dicionario simples."""
    if isinstance(registro, dict):
        return dict(registro)
    campos = getattr(registro, "dtype", None)
    if campos is not None and getattr(campos, "names", None):
        return {nome: registro[nome].item() if hasattr(registro[nome], "item")
                else registro[nome] for nome in campos.names}
    if hasattr(registro, "_asdict"):
        return dict(registro._asdict())
    return {k: getattr(registro, k) for k in dir(registro) if not k.startswith("_")}
