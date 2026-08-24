"""O registrador: escreve o log e alimenta o painel de saude.

Tres compromissos, nesta ordem:

1. **nunca derruba quem chamou.** Log e' observacao, nao operacao: se o disco
   encher no meio de um pregao, a ordem tem que sair mesmo assim. Falha de
   escrita e' contada e sinalizada, nunca levantada;
2. **append-only**, uma linha JSON por evento, um arquivo por pregao - o mesmo
   formato do Diario de Trades, que ja se provou;
3. **alimenta a Telemetria** do System Health. Antes disto, um erro so existia
   se alguem estivesse olhando na hora; agora ele aparece no painel e fica no
   arquivo.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Deque, Mapping, Optional, Sequence

from ...models import BRT
from .modelos import EventoDeLog
from .niveis import Nivel

MEMORIA_PADRAO = 500
PASTA_PADRAO = Path("logs")


class Registrador:
    """Escreve eventos de log. Injetavel; sem estado global."""

    def __init__(
        self,
        pasta: Optional[Path | str] = PASTA_PADRAO,
        nivel_minimo: Nivel = Nivel.INFO,
        telemetria=None,
        console: bool = False,
        prefixo: str = "cashinho",
        memoria: int = MEMORIA_PADRAO,
        relogio: Optional[Callable[[], datetime]] = None,
        niveis_por_componente: Optional[Mapping[str, Nivel]] = None,
    ):
        self.pasta = Path(pasta) if pasta is not None else None
        self.nivel_minimo = nivel_minimo
        self.telemetria = telemetria
        self.console = console
        self.prefixo = prefixo
        self.niveis_por_componente = dict(niveis_por_componente or {})
        self._relogio = relogio or (lambda: datetime.now(BRT))
        self._recentes: Deque[EventoDeLog] = deque(maxlen=memoria)
        self.falhas_de_escrita = 0
        self.motivo_da_falha = ""

    # ------------------------------------------------------------------
    def arquivo_do_dia(self, dia: Optional[date] = None) -> Optional[Path]:
        if self.pasta is None:
            return None
        quando = dia or self._relogio().date()
        return self.pasta / f"{self.prefixo}-{quando.isoformat()}.jsonl"

    def limiar(self, componente: str) -> Nivel:
        """O nivel minimo deste componente - com o global como padrao."""
        return self.niveis_por_componente.get(componente, self.nivel_minimo)

    # ------------------------------------------------------------------
    def registrar(self, nivel: Nivel, componente: str, mensagem: str,
                  **dados: Any) -> Optional[EventoDeLog]:
        """Grava um evento. Devolve ``None`` quando o nivel nao passa do limiar."""
        if nivel.peso < self.limiar(componente).peso:
            return None

        evento = EventoDeLog(self._relogio(), nivel, componente, str(mensagem), dados)
        self._recentes.append(evento)
        self._escrever(evento)
        self._avisar_telemetria(evento)
        if self.console:
            print(str(evento))
        return evento

    def debug(self, componente: str, mensagem: str, **dados: Any):
        return self.registrar(Nivel.DEBUG, componente, mensagem, **dados)

    def info(self, componente: str, mensagem: str, **dados: Any):
        return self.registrar(Nivel.INFO, componente, mensagem, **dados)

    def aviso(self, componente: str, mensagem: str, **dados: Any):
        return self.registrar(Nivel.AVISO, componente, mensagem, **dados)

    def erro(self, componente: str, mensagem: str, **dados: Any):
        return self.registrar(Nivel.ERRO, componente, mensagem, **dados)

    # ------------------------------------------------------------------
    def _escrever(self, evento: EventoDeLog) -> None:
        destino = self.arquivo_do_dia(evento.ts.date())
        if destino is None:
            return
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            with destino.open("a", encoding="utf-8") as fh:
                fh.write(evento.para_linha() + "\n")
        except OSError as e:
            # log que derruba o robo e' pior que log nenhum
            self.falhas_de_escrita += 1
            self.motivo_da_falha = str(e)

    def _avisar_telemetria(self, evento: EventoDeLog) -> None:
        if self.telemetria is None or evento.nivel is not Nivel.ERRO:
            return
        try:
            self.telemetria.erro(evento.componente, evento.mensagem)
        except Exception:  # telemetria quebrada nao pode quebrar o log
            pass

    # ------------------------------------------------------------------
    @property
    def recentes(self) -> tuple[EventoDeLog, ...]:
        """Os ultimos eventos que passaram por aqui, do mais novo ao mais velho."""
        return tuple(reversed(self._recentes))

    @property
    def gravando(self) -> bool:
        return self.pasta is not None and self.falhas_de_escrita == 0

    def filtrar(self, nivel: Optional[Nivel] = None, componente: str = "",
                desde: Optional[datetime] = None) -> tuple[EventoDeLog, ...]:
        achados = [
            e for e in self.recentes
            if (nivel is None or e.nivel.peso >= nivel.peso)
            and (not componente or e.componente == componente)
            and (desde is None or e.ts >= desde)
        ]
        return tuple(achados)

    def para_dict(self) -> dict:
        arquivo = self.arquivo_do_dia()
        return {
            "arquivo": str(arquivo) if arquivo else None,
            "nivel_minimo": self.nivel_minimo.value,
            "niveis_por_componente": {k: v.value for k, v in
                                      self.niveis_por_componente.items()},
            "gravando": self.gravando,
            "falhas_de_escrita": self.falhas_de_escrita,
            "motivo_da_falha": self.motivo_da_falha,
            "em_memoria": len(self._recentes),
        }


class RegistradorNulo(Registrador):
    """Nao grava nada. E' o padrao de quem nao configurou log.

    Existe para o resto do codigo poder chamar ``log.info(...)`` sem ter que
    perguntar antes se ha logger - e sem que a ausencia de configuracao vire
    escrita em disco surpresa.
    """

    def __init__(self, **campos):
        campos.setdefault("pasta", None)
        super().__init__(**campos)

    @property
    def gravando(self) -> bool:  # type: ignore[override]
        return False


def ler(caminho: Path | str) -> tuple[tuple[EventoDeLog, ...], tuple[str, ...]]:
    """Le um arquivo de log. Devolve (eventos, linhas descartadas).

    Linha corrompida nao derruba a leitura - mas tambem nao some: ela volta na
    segunda posicao da tupla, com o motivo, para quem le poder mostrar.
    """
    origem = Path(caminho)
    if not origem.exists():
        # arquivo que nao existe nao e' linha corrompida: sao coisas
        # diferentes e a tela precisa dizer coisas diferentes
        return (), ()

    eventos: list[EventoDeLog] = []
    descartadas: list[str] = []
    for i, linha in enumerate(origem.read_text(encoding="utf-8").splitlines(), start=1):
        linha = linha.strip()
        if not linha:
            continue
        try:
            eventos.append(EventoDeLog.de_dict(json.loads(linha)))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            descartadas.append(f"linha {i}: {e}")
    return tuple(eventos), tuple(descartadas)
