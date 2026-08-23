"""Os estados de uma oportunidade."""

from __future__ import annotations

from enum import Enum


class EstadoOportunidade(str, Enum):
    APROVADO = "SETUP APROVADO"
    AGUARDANDO_GATILHO = "AGUARDANDO GATILHO"
    REJEITADO = "SETUP REJEITADO"
    NAO_OPERAR = "NAO OPERAR"
    EXPIRADO = "EXPIRADO"

    @property
    def acionavel(self) -> bool:
        """So o setup aprovado pede uma decisao agora."""
        return self is EstadoOportunidade.APROVADO

    @property
    def vale_acompanhar(self) -> bool:
        return self in (EstadoOportunidade.APROVADO, EstadoOportunidade.AGUARDANDO_GATILHO)

    @property
    def descricao(self) -> str:
        return {
            EstadoOportunidade.APROVADO: "todas as condicoes atendidas - decisao e' sua",
            EstadoOportunidade.AGUARDANDO_GATILHO: "o setup esta pronto, falta o gatilho disparar",
            EstadoOportunidade.REJEITADO: "ha setup, mas ele nao passa nos criterios minimos",
            EstadoOportunidade.NAO_OPERAR: "o mercado nao esta em condicao de operar este ativo",
            EstadoOportunidade.EXPIRADO: "a janela desta oportunidade passou",
        }[self]
