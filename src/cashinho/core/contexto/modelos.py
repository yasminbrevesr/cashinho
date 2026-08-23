"""Os objetos do contexto de mercado - com o ``MarketContext`` no fim.

O contexto **descreve o ambiente**. Ele nao aponta ativo, nao sugere entrada e
nao tem preco de stop: essas coisas moram na estrategia, na oportunidade e no
risco. Aqui so existe a pergunta "como esta o mercado agora, e o quanto disso
eu realmente sei".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence

from .instrumentos import Instrumento, Papel


class EstadoDaLeitura(str, Enum):
    """O que aconteceu quando tentamos ler um instrumento."""

    OK = "ok"
    ATRASADA = "atrasada"        # veio, mas velha demais para o instante pedido
    INDISPONIVEL = "indisponivel"  # a fonte existe e falhou/nao respondeu
    SEM_FONTE = "sem_fonte"      # nao ha fonte confiavel declarada
    SIMULADA = "simulada"        # dado de demonstracao, nao e' cotacao real

    @property
    def tem_numero(self) -> bool:
        return self in (EstadoDaLeitura.OK, EstadoDaLeitura.ATRASADA,
                        EstadoDaLeitura.SIMULADA)

    @property
    def rotulo(self) -> str:
        return {
            "ok": "ok",
            "atrasada": "atrasada",
            "indisponivel": "indisponivel",
            "sem_fonte": "FONTE A CONFIRMAR",
            "simulada": "SIMULADA",
        }[self.value]


class DirecaoDeMercado(str, Enum):
    ALTA = "alta"
    BAIXA = "baixa"
    LATERAL = "lateral"
    INDISPONIVEL = "indisponivel"

    @property
    def rotulo(self) -> str:
        return {"alta": "ALTA", "baixa": "BAIXA", "lateral": "LATERAL",
                "indisponivel": "INDISPONIVEL"}[self.value]

    @property
    def conhecida(self) -> bool:
        return self is not DirecaoDeMercado.INDISPONIVEL


class NivelDeVolatilidade(str, Enum):
    BAIXA = "baixa"
    NORMAL = "normal"
    ALTA = "alta"
    EXTREMA = "extrema"
    INDISPONIVEL = "indisponivel"

    @property
    def rotulo(self) -> str:
        return self.value.upper()

    @property
    def conhecida(self) -> bool:
        return self is not NivelDeVolatilidade.INDISPONIVEL


class RegimeDeMercado(str, Enum):
    """O ambiente, em uma palavra."""

    RISCO_LIGADO = "risco_ligado"
    RISCO_DESLIGADO = "risco_desligado"
    LATERAL = "lateral"
    CONFLITANTE = "conflitante"
    ESTRESSE = "estresse"
    INDEFINIDO = "indefinido"

    @property
    def rotulo(self) -> str:
        return {
            "risco_ligado": "RISCO LIGADO",
            "risco_desligado": "RISCO DESLIGADO",
            "lateral": "LATERAL",
            "conflitante": "SINAIS CONFLITANTES",
            "estresse": "ESTRESSE",
            "indefinido": "INDEFINIDO",
        }[self.value]

    @property
    def descricao(self) -> str:
        return {
            "risco_ligado": "bolsa em alta com cambio comportado: ambiente favorece compra",
            "risco_desligado": "bolsa em baixa com dolar em alta: ambiente favorece venda",
            "lateral": "sem direcao definida no indice",
            "conflitante": "bolsa e cambio no mesmo sentido: a leitura de ambiente perde forca",
            "estresse": "volatilidade fora do normal: o mercado esta caro de operar",
            "indefinido": "dados insuficientes para afirmar qualquer regime",
        }[self.value]

    @property
    def conhecido(self) -> bool:
        return self is not RegimeDeMercado.INDEFINIDO


class NivelDeQualidade(str, Enum):
    BOA = "boa"
    PARCIAL = "parcial"
    RUIM = "ruim"
    SIMULADA = "simulada"
    INDISPONIVEL = "indisponivel"

    @property
    def rotulo(self) -> str:
        return self.value.upper()

    @property
    def confiavel(self) -> bool:
        """Da para usar este contexto para pesar uma leitura?

        SIMULADA fica de fora de proposito: dado de demonstracao nao pode
        influenciar decisao nenhuma, nem para o bem.
        """
        return self in (NivelDeQualidade.BOA, NivelDeQualidade.PARCIAL)


@dataclass(frozen=True)
class Leitura:
    """O que sabemos de um instrumento neste instante."""

    instrumento: Instrumento
    estado: EstadoDaLeitura
    ultimo: Optional[float] = None
    variacao_pct: Optional[float] = None  # no dia, quando da para calcular
    ts: Optional[datetime] = None
    defasagem_minutos: Optional[int] = None
    fonte: str = ""
    detalhe: str = ""

    @property
    def chave(self) -> str:
        return self.instrumento.chave

    @property
    def mensuravel(self) -> bool:
        """Tem numero com que dar para calcular direcao, volatilidade, correlacao.

        Inclui o dado simulado de proposito: a tela de demonstracao precisa
        exibir uma leitura completa. O que o simulado NAO pode e' influenciar
        decisao - e esse portao fica em ``QualidadeDeDados.confiavel``, um
        lugar so, em vez de espalhado por cada conta.
        """
        return self.estado.tem_numero

    @property
    def utilizavel(self) -> bool:
        """E' dado real de mercado (nao simulado, nao ausente)."""
        return self.estado in (EstadoDaLeitura.OK, EstadoDaLeitura.ATRASADA)

    @property
    def direcao(self) -> DirecaoDeMercado:
        if self.variacao_pct is None or not self.mensuravel:
            return DirecaoDeMercado.INDISPONIVEL
        if self.variacao_pct > 0.15:
            return DirecaoDeMercado.ALTA
        if self.variacao_pct < -0.15:
            return DirecaoDeMercado.BAIXA
        return DirecaoDeMercado.LATERAL

    def para_dict(self) -> dict:
        return {
            "chave": self.chave,
            "nome": self.instrumento.nome,
            "papel": self.instrumento.papel.value,
            "estado": self.estado.value,
            "ultimo": self.ultimo,
            "variacao_pct": None if self.variacao_pct is None else round(self.variacao_pct, 3),
            "ts": self.ts.isoformat() if self.ts else None,
            "defasagem_minutos": self.defasagem_minutos,
            "fonte": self.fonte,
            "detalhe": self.detalhe,
        }


@dataclass(frozen=True)
class Correlacao:
    """Correlacao entre dois instrumentos, com o tamanho da amostra junto.

    Correlacao sem amostra e' opiniao: por isso ``amostra`` nao e' opcional e
    aparece em toda exibicao.
    """

    a: str
    b: str
    valor: float  # -1..1
    amostra: int
    janela: str

    @property
    def forca(self) -> str:
        v = abs(self.valor)
        if v >= 0.7:
            return "forte"
        if v >= 0.4:
            return "moderada"
        return "fraca"

    @property
    def sentido(self) -> str:
        return "inversa" if self.valor < 0 else "direta"

    def para_dict(self) -> dict:
        return {
            "a": self.a, "b": self.b, "valor": round(self.valor, 3),
            "amostra": self.amostra, "janela": self.janela,
            "forca": self.forca, "sentido": self.sentido,
        }


@dataclass(frozen=True)
class QualidadeDeDados:
    """Quanto do contexto realmente chegou - e quao fresco."""

    nivel: NivelDeQualidade
    disponiveis: int
    esperados: int
    faltantes: tuple[str, ...] = ()
    sem_fonte: tuple[str, ...] = ()
    defasagem_minutos: Optional[int] = None
    notas: tuple[str, ...] = ()

    @property
    def cobertura(self) -> float:
        return self.disponiveis / self.esperados if self.esperados else 0.0

    @property
    def confiavel(self) -> bool:
        return self.nivel.confiavel

    @property
    def resumo(self) -> str:
        partes = [f"{self.disponiveis} de {self.esperados} fontes"]
        if self.defasagem_minutos is not None:
            partes.append(f"atraso {self.defasagem_minutos} min")
        if self.sem_fonte:
            partes.append(f"{len(self.sem_fonte)} sem fonte confirmada")
        return " · ".join(partes)

    def para_dict(self) -> dict:
        return {
            "nivel": self.nivel.value,
            "disponiveis": self.disponiveis,
            "esperados": self.esperados,
            "cobertura": round(self.cobertura, 3),
            "faltantes": list(self.faltantes),
            "sem_fonte": list(self.sem_fonte),
            "defasagem_minutos": self.defasagem_minutos,
            "confiavel": self.confiavel,
            "notas": list(self.notas),
        }


@dataclass(frozen=True)
class MarketContext:
    """O ambiente de mercado em um instante.

    Nao gera operacao. Nao tem entrada, stop nem alvo - e nao ha metodo aqui
    que produza qualquer um dos tres. E' um insumo, e so.
    """

    timestamp: datetime
    market_regime: RegimeDeMercado
    ibovespa_direction: DirecaoDeMercado
    volatility: NivelDeVolatilidade
    relevant_correlations: tuple[Correlacao, ...]
    data_quality: QualidadeDeDados

    # leitura detalhada, para a tela e para quem quiser olhar instrumento a
    # instrumento; nao faz parte do contrato pedido
    leituras: tuple[Leitura, ...] = ()
    notas: tuple[str, ...] = ()
    criterio_correlacao: str = ""  # o que contou como relevante nesta leitura

    # -- consultas ------------------------------------------------------
    def leitura(self, chave: str) -> Optional[Leitura]:
        for l in self.leituras:
            if l.chave == chave:
                return l
        return None

    def por_papel(self, papel: Papel) -> tuple[Leitura, ...]:
        return tuple(l for l in self.leituras if l.instrumento.papel is papel)

    @property
    def utilizavel(self) -> bool:
        """Este contexto pode pesar numa leitura de ativo?"""
        return self.data_quality.confiavel and self.market_regime.conhecido

    @property
    def favorece_compra(self) -> bool:
        return self.utilizavel and self.market_regime is RegimeDeMercado.RISCO_LIGADO

    @property
    def favorece_venda(self) -> bool:
        return self.utilizavel and self.market_regime is RegimeDeMercado.RISCO_DESLIGADO

    @property
    def alerta_de_estresse(self) -> bool:
        return self.market_regime is RegimeDeMercado.ESTRESSE

    def para_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "market_regime": self.market_regime.value,
            "ibovespa_direction": self.ibovespa_direction.value,
            "volatility": self.volatility.value,
            "relevant_correlations": [c.para_dict() for c in self.relevant_correlations],
            "data_quality": self.data_quality.para_dict(),
            "leituras": [l.para_dict() for l in self.leituras],
            "notas": list(self.notas),
            "criterio_correlacao": self.criterio_correlacao,
            "utilizavel": self.utilizavel,
        }
