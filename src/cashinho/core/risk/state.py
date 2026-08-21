"""Estado do risco: posicoes abertas, resultado do dia, sequencia de perdas e drawdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from ...models import BRT
from .models import KillSwitch, Position, TradeResult


def _hoje() -> date:
    return datetime.now(BRT).date()


@dataclass
class RiskState:
    """Tudo o que muda ao longo do pregao.

    ``capital_pregao`` congela o patrimonio da abertura: a perda maxima
    diaria e' medida sobre ele, e nao sobre o patrimonio que encolhe durante
    o dia - senao o limite se mexeria junto com o prejuizo.
    """

    capital_inicial: float
    patrimonio: float = 0.0
    capital_pregao: float = 0.0
    pico: float = 0.0
    pregao: date = field(default_factory=_hoje)
    pnl_dia: float = 0.0
    trades_dia: int = 0
    perdas_consecutivas: int = 0
    posicoes: dict[str, Position] = field(default_factory=dict)
    kill_switch: Optional[KillSwitch] = None
    historico: list[TradeResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capital_inicial <= 0:
            raise ValueError("capital_inicial precisa ser maior que zero")
        if not self.patrimonio:
            self.patrimonio = self.capital_inicial
        if not self.capital_pregao:
            self.capital_pregao = self.patrimonio
        if not self.pico:
            self.pico = self.patrimonio

    # ------------------------------------------------------------------
    # exposicao
    # ------------------------------------------------------------------
    def exposicao_total(self) -> float:
        return sum(p.exposicao for p in self.posicoes.values())

    def exposicao_de(self, symbol: str) -> float:
        p = self.posicoes.get(symbol.upper())
        return p.exposicao if p else 0.0

    def tem_posicao(self, symbol: str) -> bool:
        return symbol.upper() in self.posicoes

    def caixa_disponivel(self) -> float:
        return max(self.patrimonio - self.exposicao_total(), 0.0)

    # ------------------------------------------------------------------
    # drawdown
    # ------------------------------------------------------------------
    @property
    def drawdown(self) -> float:
        return max(self.pico - self.patrimonio, 0.0)

    @property
    def drawdown_pct(self) -> float:
        return (self.drawdown / self.pico * 100.0) if self.pico else 0.0

    # ------------------------------------------------------------------
    # ciclo de vida das posicoes
    # ------------------------------------------------------------------
    def registrar_abertura(self, posicao: Position) -> None:
        chave = posicao.symbol.upper()
        if chave in self.posicoes:
            raise ValueError(f"ja existe posicao aberta em {chave}")
        self.posicoes[chave] = posicao
        self.trades_dia += 1

    def registrar_fechamento(self, trade: TradeResult) -> None:
        chave = trade.symbol.upper()
        self.posicoes.pop(chave, None)
        self.historico.append(trade)
        self.pnl_dia += trade.resultado
        self.patrimonio += trade.resultado
        self.pico = max(self.pico, self.patrimonio)
        if trade.perdeu:
            self.perdas_consecutivas += 1
        else:
            self.perdas_consecutivas = 0

    # ------------------------------------------------------------------
    # pregao
    # ------------------------------------------------------------------
    def novo_pregao(self, dia: Optional[date] = None) -> None:
        """Zera os contadores do dia e desarma as travas diarias.

        Posicoes abertas, patrimonio, pico e a sequencia de perdas atravessam
        o dia - so o que e' diario reinicia.
        """
        self.pregao = dia or _hoje()
        self.pnl_dia = 0.0
        self.trades_dia = 0
        self.capital_pregao = self.patrimonio
        if self.kill_switch is not None and self.kill_switch.diario:
            self.kill_switch = None

    def para_dict(self) -> dict:
        return {
            "capital_inicial": round(self.capital_inicial, 2),
            "patrimonio": round(self.patrimonio, 2),
            "capital_pregao": round(self.capital_pregao, 2),
            "pico": round(self.pico, 2),
            "pregao": self.pregao.isoformat(),
            "pnl_dia": round(self.pnl_dia, 2),
            "trades_dia": self.trades_dia,
            "perdas_consecutivas": self.perdas_consecutivas,
            "drawdown": round(self.drawdown, 2),
            "posicoes": sorted(self.posicoes),
            "kill_switch": self.kill_switch.para_dict() if self.kill_switch else None,
        }

    def ajustar_capital(self, novo_capital: float) -> None:
        """Aporte ou retirada: move patrimonio e pico juntos, sem criar drawdown."""
        if novo_capital <= 0:
            raise ValueError("capital precisa ser maior que zero")
        delta = novo_capital - self.capital_inicial
        self.capital_inicial = novo_capital
        self.patrimonio += delta
        self.capital_pregao += delta
        self.pico += delta

    @classmethod
    def de_dict(cls, dados: dict) -> "RiskState":
        """Reconstroi o estado salvo em disco.

        O historico de trades nao volta (so os agregados que os limites usam:
        patrimonio, pico, resultado do dia, contadores e posicoes abertas).
        """
        from datetime import datetime as _dt

        from ...models import Direction

        estado = cls(
            capital_inicial=float(dados["capital_inicial"]),
            patrimonio=float(dados.get("patrimonio") or 0.0),
            capital_pregao=float(dados.get("capital_pregao") or 0.0),
            pico=float(dados.get("pico") or 0.0),
            pregao=date.fromisoformat(dados["pregao"]) if dados.get("pregao") else _hoje(),
            pnl_dia=float(dados.get("pnl_dia", 0.0)),
            trades_dia=int(dados.get("trades_dia", 0)),
            perdas_consecutivas=int(dados.get("perdas_consecutivas", 0)),
        )
        for p in dados.get("posicoes_abertas", []):
            estado.posicoes[p["symbol"]] = Position(
                symbol=p["symbol"],
                direcao=Direction(p["direcao"]),
                quantidade=int(p["quantidade"]),
                preco_medio=float(p["preco_medio"]),
                stop=float(p["stop"]),
                aberta_em=_dt.fromisoformat(p["aberta_em"]),
            )
        ks = dados.get("kill_switch")
        if ks:
            estado.kill_switch = KillSwitch(
                codigo=ks["codigo"],
                motivo=ks["motivo"],
                acionado_em=_dt.fromisoformat(ks["acionado_em"]),
                diario=bool(ks.get("diario", False)),
            )
        return estado

    def para_dict_completo(self) -> dict:
        """Como :meth:`para_dict`, mas com as posicoes inteiras (para salvar)."""
        dados = self.para_dict()
        dados["posicoes_abertas"] = [
            {
                "symbol": p.symbol,
                "direcao": p.direcao.value,
                "quantidade": p.quantidade,
                "preco_medio": p.preco_medio,
                "stop": p.stop,
                "aberta_em": p.aberta_em.isoformat(),
            }
            for p in self.posicoes.values()
        ]
        return dados
