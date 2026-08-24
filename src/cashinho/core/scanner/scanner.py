"""Scanner B3: varre a watchlist e ranqueia o que sobrou.

Por ativo, oito etapas na ordem:

    Market Data -> Context -> Multi-Timeframe -> Strategy -> Opportunity
                -> Score -> Auditor -> Risk Manager

As tres primeiras sao do scanner (buscar dados, filtrar e alinhar
timeframes); as cinco ultimas sao o :class:`Pipeline` que ja existia. Cada
ativo carrega a trilha inteira, entao da para ver exatamente onde cada um
parou - e "nenhuma oportunidade encontrada" e' um resultado legitimo, com
motivos, nao um erro.

O Risk Manager e' **um so** para a varredura inteira: perda diaria, numero de
trades e exposicao sao limites da carteira, nao do ativo. Como o scanner
apenas avalia (nao abre posicao), a ordem dos ativos nao muda o resultado -
mas abrir uma das oportunidades muda o que sobra para as outras.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional, Sequence

from ...data.base import DataError, Provider
from ...models import BRT, Direction, Series
from ..auditor.auditor import ContrarianAuditor
from ..auditor.modelos import AuditResult
from ..auditor.pipeline import Etapa, Pipeline, ResultadoFinal
from ..confluencia import MultiTimeframeEngine
from ..oportunidade.engine import OpportunityEngine
from ..oportunidade.estados import EstadoOportunidade
from ..oportunidade.modelos import Opportunity
from ..oportunidade.estrategia import EstrategiaOportunidade
from ..risk import RiskConfig, RiskDecision, RiskManager, RiskState
from ..strategy.base import Strategy
from .config import ScannerConfig
from .filtros import Filtro, aplicar


class StatusAtivo(str, Enum):
    """Onde o ativo parou - e' a coluna Status da tela."""

    LIBERADO = "LIBERADO"
    BARRADO_RISCO = "BARRADO NO RISCO"
    BARRADO_AUDITOR = "BARRADO NO AUDITOR"
    AGUARDANDO = "AGUARDANDO GATILHO"
    REJEITADO = "SETUP REJEITADO"
    SEM_SETUP = "SEM SETUP"
    FILTRADO = "FILTRADO"
    SEM_DADOS = "SEM DADOS"
    ERRO = "ERRO"

    @property
    def operavel(self) -> bool:
        """Vale a pena aparecer para quem opera agora."""
        return self in (StatusAtivo.LIBERADO, StatusAtivo.AGUARDANDO)

    @property
    def analisado(self) -> bool:
        """Chegou a rodar o pipeline (nao foi cortado antes)."""
        return self not in (StatusAtivo.FILTRADO, StatusAtivo.SEM_DADOS, StatusAtivo.ERRO)


@dataclass
class LinhaScanner:
    """Um ativo no resultado da varredura."""

    symbol: str
    status: StatusAtivo
    motivo: str = ""
    filtros: list[Filtro] = field(default_factory=list)
    etapas: list[Etapa] = field(default_factory=list)
    oportunidade: Optional[Opportunity] = None
    auditoria: Optional[AuditResult] = None
    risco: Optional[RiskDecision] = None
    timestamp: Optional[datetime] = None

    # -- colunas da tela ------------------------------------------------
    @property
    def score(self) -> float:
        if self.auditoria is not None:
            return self.auditoria.score_final
        return self.oportunidade.score if self.oportunidade else 0.0

    @property
    def setup(self) -> str:
        return self.oportunidade.setup if self.oportunidade else "-"

    @property
    def direcao(self) -> Optional[Direction]:
        return self.oportunidade.direction if self.oportunidade else None

    @property
    def timeframe(self) -> str:
        return self.oportunidade.timeframe_setup if self.oportunidade else "-"

    @property
    def rr(self) -> float:
        return self.oportunidade.risk_reward if self.oportunidade else 0.0

    @property
    def risco_por_acao(self) -> float:
        return self.oportunidade.risco_por_acao if self.oportunidade else 0.0

    @property
    def risco_financeiro(self) -> float:
        """Quanto se perde se o stop bater, ja com a quantidade do risco."""
        if self.risco is not None and self.risco.allowed:
            return self.risco.monetary_risk
        return 0.0

    @property
    def quantidade(self) -> int:
        return self.risco.position_size if self.risco and self.risco.allowed else 0

    def para_dict(self) -> dict:
        return {
            "ativo": self.symbol,
            "status": self.status.value,
            "score": round(self.score, 1),
            "setup": self.setup,
            "direcao": self.direcao.value if self.direcao else None,
            "timeframe": self.timeframe,
            "rr": round(self.rr, 2),
            "risco_por_acao": round(self.risco_por_acao, 4),
            "risco_financeiro": round(self.risco_financeiro, 2),
            "quantidade": self.quantidade,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "motivo": self.motivo,
            "filtros": [f.para_dict() for f in self.filtros],
            "etapas": [
                {"ordem": e.ordem, "nome": e.nome, "passou": e.passou,
                 "executada": e.executada, "detalhe": e.detalhe}
                for e in self.etapas
            ],
        }


@dataclass
class ResultadoScanner:
    """A varredura inteira."""

    instante: datetime
    linhas: list[LinhaScanner] = field(default_factory=list)
    config: ScannerConfig = field(default_factory=ScannerConfig)
    avisos: list[str] = field(default_factory=list)

    @property
    def oportunidades(self) -> list[LinhaScanner]:
        """Ativos que chegaram ao fim do fluxo liberados."""
        return [l for l in self.linhas if l.status is StatusAtivo.LIBERADO]

    @property
    def acompanhar(self) -> list[LinhaScanner]:
        return [l for l in self.linhas if l.status is StatusAtivo.AGUARDANDO]

    @property
    def tem_oportunidades(self) -> bool:
        return bool(self.oportunidades)

    @property
    def analisados(self) -> list[LinhaScanner]:
        return [l for l in self.linhas if l.status.analisado]

    @property
    def filtrados(self) -> list[LinhaScanner]:
        return [l for l in self.linhas if not l.status.analisado]

    def ranking(self, ordenar_por: Optional[str] = None,
                apenas_operaveis: Optional[bool] = None,
                limite: Optional[int] = None) -> list[LinhaScanner]:
        """A watchlist ordenada. Por score, do maior para o menor, por padrao."""
        criterio = ordenar_por or self.config.ordenar_por
        operaveis = self.config.apenas_operaveis if apenas_operaveis is None else apenas_operaveis
        linhas = [l for l in self.linhas if l.status.operavel] if operaveis else list(self.linhas)

        chaves = {
            "score": lambda l: (-l.score, l.symbol),
            "rr": lambda l: (-l.rr, l.symbol),
            "risco": lambda l: (l.risco_financeiro or float("inf"), l.symbol),
            "ativo": lambda l: (l.symbol,),
            "status": lambda l: (_ORDEM_STATUS.index(l.status), -l.score, l.symbol),
        }
        linhas.sort(key=chaves.get(criterio, chaves["score"]))
        limite = limite if limite is not None else self.config.max_resultados
        return linhas[:limite] if limite else linhas

    @property
    def resumo(self) -> str:
        if self.tem_oportunidades:
            nomes = ", ".join(l.symbol for l in self.oportunidades)
            return f"{len(self.oportunidades)} oportunidade(s) liberada(s): {nomes}"
        if self.acompanhar:
            nomes = ", ".join(l.symbol for l in self.acompanhar)
            return f"nenhuma oportunidade liberada; {len(self.acompanhar)} para acompanhar: {nomes}"
        return "nenhuma oportunidade encontrada nesta varredura"

    def para_dict(self) -> dict:
        return {
            "instante": self.instante.isoformat(),
            "tem_oportunidades": self.tem_oportunidades,
            "resumo": self.resumo,
            "watchlist": list(self.config.watchlist),
            "ordenado_por": self.config.ordenar_por,
            "linhas": [l.para_dict() for l in self.ranking()],
            "avisos": list(self.avisos),
        }


_ORDEM_STATUS = (
    StatusAtivo.LIBERADO,
    StatusAtivo.AGUARDANDO,
    StatusAtivo.BARRADO_RISCO,
    StatusAtivo.BARRADO_AUDITOR,
    StatusAtivo.REJEITADO,
    StatusAtivo.SEM_SETUP,
    StatusAtivo.FILTRADO,
    StatusAtivo.SEM_DADOS,
    StatusAtivo.ERRO,
)


class ScannerB3:
    """Varre a watchlist com o pipeline existente."""

    PRE_ETAPAS = ("Market Data", "Context", "Multi-Timeframe")

    def __init__(
        self,
        provider: Provider,
        config: Optional[ScannerConfig] = None,
        estrategia: Optional[Strategy] = None,
        engine: Optional[OpportunityEngine] = None,
        auditor: Optional[ContrarianAuditor] = None,
        risco: Optional[RiskManager] = None,
        log=None,
    ):
        from ..log import RegistradorNulo

        self.log = log or RegistradorNulo()
        self.provider = provider
        self.config = config or ScannerConfig()
        self.engine = engine or OpportunityEngine()
        self.estrategia = estrategia or EstrategiaOportunidade(self.engine)
        self.auditor = auditor or ContrarianAuditor()
        self.risco = risco or RiskManager(
            RiskConfig(capital=100_000.0), RiskState(capital_inicial=100_000.0)
        )
        self.pipeline = Pipeline(self.estrategia, self.engine, self.auditor, self.risco)

    # ------------------------------------------------------------------
    def varrer(
        self,
        agora: Optional[datetime] = None,
        spreads: Optional[Mapping[str, float]] = None,
    ) -> ResultadoScanner:
        """Analisa a watchlist inteira e devolve o ranking."""
        spreads = spreads or {}
        resultado = ResultadoScanner(
            instante=agora or datetime.now(BRT), config=self.config, linhas=[]
        )
        for symbol in self.config.watchlist:
            resultado.linhas.append(
                self._analisar(symbol, agora, spreads.get(symbol.upper()))
            )
        if not resultado.analisados:
            resultado.avisos.append(
                "nenhum ativo passou dos filtros iniciais - confira liquidez, "
                "volatilidade e a fonte de dados"
            )
        return resultado

    # ------------------------------------------------------------------
    def _analisar(self, symbol: str, agora: Optional[datetime],
                  spread_ticks: Optional[float]) -> LinhaScanner:
        etapas: list[Etapa] = []

        # 1) Market Data --------------------------------------------------
        try:
            serie = self.provider.candles(symbol, self.config.timeframe_base, self.config.dias)
        except DataError as e:
            # o ativo cai fora da varredura; sem log, a falha desaparecia
            # junto com o resultado da varredura
            self.log.erro("market_data", f"{symbol}: {e}", symbol=symbol)
            etapas.append(Etapa(1, "Market Data", False, str(e)))
            return LinhaScanner(symbol, StatusAtivo.SEM_DADOS, str(e),
                                etapas=self._pendentes(etapas, 1))
        if len(serie) == 0:
            etapas.append(Etapa(1, "Market Data", False, "serie vazia"))
            return LinhaScanner(symbol, StatusAtivo.SEM_DADOS, "serie vazia",
                                etapas=self._pendentes(etapas, 1))
        etapas.append(Etapa(1, "Market Data", True, f"{len(serie)} candles de {self.config.timeframe_base}"))

        # 2) Context (filtros iniciais) -------------------------------------
        filtros = aplicar(serie, self.config, agora, spread_ticks)
        cortes = [f for f in filtros if not f.passou]
        if cortes:
            motivo = "; ".join(f"{f.titulo}: {f.detalhe}" for f in cortes)
            etapas.append(Etapa(2, "Context", False, motivo))
            return LinhaScanner(symbol, StatusAtivo.FILTRADO, motivo, filtros,
                                self._pendentes(etapas, 2), timestamp=serie.last.ts)
        etapas.append(Etapa(2, "Context", True, "passou nos filtros iniciais"))

        # 3) Multi-Timeframe -------------------------------------------------
        try:
            mtf = self.engine.alimentar(serie)
            vista = mtf.em(agora) if agora else mtf.agora()
        except Exception as e:  # serie curta, timeframe incompativel...
            etapas.append(Etapa(3, "Multi-Timeframe", False, str(e)))
            return LinhaScanner(symbol, StatusAtivo.ERRO, str(e), filtros,
                                self._pendentes(etapas, 3), timestamp=serie.last.ts)
        etapas.append(Etapa(3, "Multi-Timeframe", True, f"alinhado em {vista.instante:%H:%M}"))

        # 4 a 8) Strategy -> Opportunity -> Score -> Auditor -> Risk Manager
        final = self.pipeline.executar(vista, symbol, agora=vista.instante)
        etapas.extend(replace(e, ordem=e.ordem + 3) for e in final.etapas)

        return LinhaScanner(
            symbol=symbol,
            status=self._status(final),
            motivo=final.resumo,
            filtros=filtros,
            etapas=etapas,
            oportunidade=final.opportunity,
            auditoria=final.auditoria,
            risco=final.decisao_de_risco,
            timestamp=vista.instante,
        )

    def _status(self, final: ResultadoFinal) -> StatusAtivo:
        if final.aprovado:
            return StatusAtivo.LIBERADO
        parada = final.parou_em
        if parada is None:
            return StatusAtivo.ERRO
        if parada.nome == "Risk Manager":
            return StatusAtivo.BARRADO_RISCO
        if parada.nome == "Auditor":
            return StatusAtivo.BARRADO_AUDITOR
        op = final.opportunity
        if op is not None:
            if op.estado is EstadoOportunidade.AGUARDANDO_GATILHO:
                return StatusAtivo.AGUARDANDO
            if op.estado is EstadoOportunidade.REJEITADO:
                return StatusAtivo.REJEITADO
        return StatusAtivo.SEM_SETUP

    def _pendentes(self, etapas: list[Etapa], ate: int) -> list[Etapa]:
        nomes = list(self.PRE_ETAPAS) + list(Pipeline.ETAPAS)
        for i, nome in enumerate(nomes[ate:], start=ate + 1):
            etapas.append(Etapa(i, nome, False, "nao executada", executada=False))
        return etapas
