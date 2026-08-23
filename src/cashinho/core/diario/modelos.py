"""O registro de uma operacao no diario.

Um registro junta duas coisas que moram em lugares diferentes: o que a
**corretora** fez (precos, quantidades, horarios, resultado) e o que a
**analise** dizia na hora da entrada (setup, score, camadas, avisos do
auditor). Sem a segunda metade, o diario vira extrato bancario - conta o
quanto, nunca o porque.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ...models import Direction

DIAS_DA_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")

MOTIVOS_DE_SAIDA = {
    "stop_loss": "stop acionado",
    "take_profit": "alvo atingido",
    "market": "encerrada a mercado",
    "limit": "encerrada por ordem limitada",
    "stop": "encerrada por ordem stop",
    "oco": "encerrada pela OCO",
}


def novo_id() -> str:
    return f"reg-{uuid.uuid4().hex[:10]}"


@dataclass(frozen=True)
class Registro:
    """Uma operacao encerrada, com o contexto que a originou."""

    # --- o que a corretora fez -----------------------------------------
    symbol: str
    direcao: Direction
    aberta_em: datetime
    fechada_em: datetime
    quantidade: int
    entrada: float
    saida: float
    custos: float
    resultado: float  # liquido de custos

    # --- o que a analise dizia ------------------------------------------
    stop: float = 0.0
    alvo: float = 0.0
    setup: str = ""
    score: float = 0.0
    timeframe_context: str = ""
    timeframe_trend: str = ""
    timeframe_setup: str = ""
    timeframe_trigger: str = ""
    motivo_entrada: tuple[str, ...] = ()
    motivo_saida: str = ""
    condicoes_de_mercado: tuple[str, ...] = ()
    warnings_auditor: tuple[str, ...] = ()

    id: str = field(default_factory=novo_id)
    observacao: str = ""

    # --- derivados --------------------------------------------------------
    @property
    def data(self) -> date:
        return self.fechada_em.date()

    @property
    def hora(self) -> int:
        """Hora da ENTRADA - e' quando a decisao foi tomada."""
        return self.aberta_em.hour

    @property
    def dia_da_semana(self) -> str:
        return DIAS_DA_SEMANA[self.aberta_em.weekday()]

    @property
    def duracao(self) -> timedelta:
        return self.fechada_em - self.aberta_em

    @property
    def duracao_minutos(self) -> float:
        return self.duracao.total_seconds() / 60.0

    @property
    def risco_por_acao(self) -> float:
        return abs(self.entrada - self.stop) if self.stop else 0.0

    @property
    def risco(self) -> float:
        """Quanto se arriscou de verdade: quantidade x distancia ate o stop."""
        return self.risco_por_acao * self.quantidade

    @property
    def retorno_planejado(self) -> float:
        return abs(self.alvo - self.entrada) * self.quantidade if self.alvo else 0.0

    @property
    def rr(self) -> float:
        return (self.retorno_planejado / self.risco) if self.risco else 0.0

    @property
    def resultado_em_r(self) -> float:
        """Resultado em multiplos do risco - a medida comparavel entre ativos."""
        return self.resultado / self.risco if self.risco else 0.0

    @property
    def resultado_bruto(self) -> float:
        return self.resultado + self.custos

    @property
    def venceu(self) -> bool:
        return self.resultado > 0

    @property
    def perdeu(self) -> bool:
        return self.resultado < 0

    @property
    def timeframes(self) -> str:
        partes = [t for t in (self.timeframe_context, self.timeframe_trend,
                              self.timeframe_setup, self.timeframe_trigger) if t]
        return "/".join(partes)

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "data": self.data.isoformat(),
            "horario": self.aberta_em.strftime("%H:%M"),
            "symbol": self.symbol,
            "direcao": self.direcao.value,
            "setup": self.setup,
            "score": round(self.score, 1),
            "timeframe_context": self.timeframe_context,
            "timeframe_trend": self.timeframe_trend,
            "timeframe_setup": self.timeframe_setup,
            "timeframe_trigger": self.timeframe_trigger,
            "entrada": round(self.entrada, 4),
            "stop": round(self.stop, 4),
            "alvo": round(self.alvo, 4),
            "quantidade": self.quantidade,
            "saida": round(self.saida, 4),
            "resultado": round(self.resultado, 2),
            "resultado_em_r": round(self.resultado_em_r, 3),
            "risco": round(self.risco, 2),
            "rr": round(self.rr, 2),
            "custos": round(self.custos, 2),
            "motivo_entrada": list(self.motivo_entrada),
            "motivo_saida": self.motivo_saida,
            "condicoes_de_mercado": list(self.condicoes_de_mercado),
            "warnings_auditor": list(self.warnings_auditor),
            "aberta_em": self.aberta_em.isoformat(),
            "fechada_em": self.fechada_em.isoformat(),
            "duracao_minutos": round(self.duracao_minutos, 1),
            "observacao": self.observacao,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Registro":
        return cls(
            symbol=dados["symbol"],
            direcao=Direction(dados["direcao"]),
            aberta_em=datetime.fromisoformat(dados["aberta_em"]),
            fechada_em=datetime.fromisoformat(dados["fechada_em"]),
            quantidade=int(dados["quantidade"]),
            entrada=float(dados["entrada"]),
            saida=float(dados["saida"]),
            custos=float(dados.get("custos", 0.0)),
            resultado=float(dados["resultado"]),
            stop=float(dados.get("stop", 0.0)),
            alvo=float(dados.get("alvo", 0.0)),
            setup=dados.get("setup", ""),
            score=float(dados.get("score", 0.0)),
            timeframe_context=dados.get("timeframe_context", ""),
            timeframe_trend=dados.get("timeframe_trend", ""),
            timeframe_setup=dados.get("timeframe_setup", ""),
            timeframe_trigger=dados.get("timeframe_trigger", ""),
            motivo_entrada=tuple(dados.get("motivo_entrada", ())),
            motivo_saida=dados.get("motivo_saida", ""),
            condicoes_de_mercado=tuple(dados.get("condicoes_de_mercado", ())),
            warnings_auditor=tuple(dados.get("warnings_auditor", ())),
            id=dados.get("id", novo_id()),
            observacao=dados.get("observacao", ""),
        )


@dataclass(frozen=True)
class Filtro:
    """Recorte do diario. Campos vazios nao filtram nada."""

    ativo: Optional[str] = None
    setup: Optional[str] = None
    timeframe: Optional[str] = None
    inicio: Optional[date] = None
    fim: Optional[date] = None
    resultado: Optional[str] = None  # "vencedor" | "perdedor" | "zerado"
    direcao: Optional[Direction] = None

    def aceita(self, r: Registro) -> bool:
        if self.ativo and r.symbol.upper() != self.ativo.strip().upper():
            return False
        if self.setup and self.setup.strip().lower() not in r.setup.lower():
            return False
        if self.timeframe and self.timeframe.strip() not in r.timeframes:
            return False
        if self.inicio and r.data < self.inicio:
            return False
        if self.fim and r.data > self.fim:
            return False
        if self.direcao and r.direcao is not self.direcao:
            return False
        if self.resultado:
            alvo = self.resultado.strip().lower()
            if alvo.startswith("venc") and not r.venceu:
                return False
            if alvo.startswith("perd") and not r.perdeu:
                return False
            if alvo.startswith("zer") and r.resultado != 0:
                return False
        return True

    @property
    def vazio(self) -> bool:
        return all(v is None for v in (self.ativo, self.setup, self.timeframe,
                                       self.inicio, self.fim, self.resultado, self.direcao))

    def descricao(self) -> str:
        if self.vazio:
            return "sem filtro"
        partes = []
        if self.ativo:
            partes.append(f"ativo {self.ativo.upper()}")
        if self.setup:
            partes.append(f"setup contendo '{self.setup}'")
        if self.timeframe:
            partes.append(f"timeframe {self.timeframe}")
        if self.inicio:
            partes.append(f"de {self.inicio:%d/%m/%Y}")
        if self.fim:
            partes.append(f"ate {self.fim:%d/%m/%Y}")
        if self.resultado:
            partes.append(f"apenas {self.resultado}")
        if self.direcao:
            partes.append(f"direcao {self.direcao.value.lower()}")
        return " · ".join(partes)
