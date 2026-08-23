"""Os tipos de evento que este modulo sabe reconhecer.

A lista e' fechada de proposito. Um evento com tipo que nao esta aqui e'
**descartado com motivo**, nunca encaixado no tipo mais parecido: classificar
por semelhanca e' o comeco de inventar notícia.
"""

from __future__ import annotations

from enum import Enum


class TipoDeEvento(str, Enum):
    """O que aconteceu (ou vai acontecer)."""

    RESULTADOS = "resultados"
    FATO_RELEVANTE = "fato_relevante"
    DECISAO_DE_JUROS = "decisao_de_juros"
    INFLACAO = "inflacao"
    PAYROLL = "payroll"
    EVENTO_CORPORATIVO = "evento_corporativo"

    @property
    def rotulo(self) -> str:
        return {
            "resultados": "Divulgacao de resultados",
            "fato_relevante": "Fato relevante",
            "decisao_de_juros": "Decisao de juros",
            "inflacao": "Inflacao",
            "payroll": "Payroll",
            "evento_corporativo": "Evento corporativo",
        }[self.value]

    @property
    def curto(self) -> str:
        return {
            "resultados": "RESULTADOS",
            "fato_relevante": "FATO RELEVANTE",
            "decisao_de_juros": "JUROS",
            "inflacao": "INFLACAO",
            "payroll": "PAYROLL",
            "evento_corporativo": "CORPORATIVO",
        }[self.value]

    @property
    def macro(self) -> bool:
        """Evento de mercado inteiro, nao de um ativo."""
        return self in (TipoDeEvento.DECISAO_DE_JUROS, TipoDeEvento.INFLACAO,
                        TipoDeEvento.PAYROLL)

    @property
    def agendavel(self) -> bool:
        """Tem hora marcada conhecida com antecedencia?

        Fato relevante nao tem: ele aparece. E' por isso que a janela de
        protecao de um fato relevante so existe DEPOIS dele.
        """
        return self is not TipoDeEvento.FATO_RELEVANTE


class Severidade(str, Enum):
    """Quanto o evento mexe com o preco."""

    CRITICA = "critica"
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"

    @property
    def rotulo(self) -> str:
        return self.value.upper()

    @property
    def peso(self) -> int:
        return {"critica": 4, "alta": 3, "media": 2, "baixa": 1}[self.value]

    def __lt__(self, outra: "Severidade") -> bool:  # type: ignore[override]
        return self.peso < outra.peso


class ViesDirecional(str, Enum):
    """Para que lado a noticia empurra - **informacao, nao ordem**.

    Este campo nunca vira compra ou venda. Ele existe para dizer que uma
    operacao esta indo contra o que a noticia sugere - o que aumenta o risco
    dela, e nada mais.
    """

    ALTA = "alta"
    BAIXA = "baixa"
    INDEFINIDO = "indefinido"

    @property
    def rotulo(self) -> str:
        return {"alta": "ALTA", "baixa": "BAIXA", "indefinido": "INDEFINIDO"}[self.value]

    @property
    def conhecido(self) -> bool:
        return self is not ViesDirecional.INDEFINIDO


class Disponibilidade(str, Enum):
    """O estado da fonte de noticias."""

    DISPONIVEL = "disponivel"
    DESATUALIZADA = "desatualizada"
    INDISPONIVEL = "indisponivel"
    SEM_FONTE = "sem_fonte"

    @property
    def confiavel(self) -> bool:
        """So agenda fresca conta para decidir."""
        return self is Disponibilidade.DISPONIVEL

    @property
    def rotulo(self) -> str:
        if self is Disponibilidade.DISPONIVEL:
            return "NOTICIAS DISPONIVEIS"
        return "NOTICIAS INDISPONIVEIS"

    @property
    def detalhe(self) -> str:
        return {
            "disponivel": "agenda carregada e dentro da validade",
            "desatualizada": "a agenda existe mas esta velha demais para valer",
            "indisponivel": "a fonte nao respondeu",
            "sem_fonte": "nenhuma fonte de noticias configurada",
        }[self.value]
