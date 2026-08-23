"""Ticket Generator da Genial: traduz uma oportunidade em boleta.

    from cashinho.core.genial import TicketGenerator, pagina

    ticket = TicketGenerator().gerar(oportunidade, decisao_de_risco)
    print(pagina(ticket))

**Nao envia ordem.** Este modulo nao conhece API, token nem endpoint da
Genial - ele produz um roteiro de digitacao. Tudo o que depende de como a
plataforma da Genial se comporta sai marcado como
``REGRA GENIAL A CONFIRMAR``.
"""

from .gerador import ConfigTicket, TicketGenerator
from .modelos import Boleta, CampoBoleta, PapelDaBoleta, ResumoOperacao, Ticket, TipoBoleta
from .regras import (
    PENDENCIAS_GENIAL,
    REGRAS_B3,
    TODAS,
    Regra,
    StatusRegra,
    pendentes,
    regra,
)
from .view import (
    SELO,
    bloco_boleta,
    bloco_para_copiar,
    faixa_nao_envia,
    pagina,
    painel_resumo,
    resumo_uma_linha,
    secao_condicoes,
    secao_pendencias,
)

__all__ = [
    "TicketGenerator",
    "ConfigTicket",
    "Ticket",
    "Boleta",
    "TipoBoleta",
    "PapelDaBoleta",
    "CampoBoleta",
    "ResumoOperacao",
    "Regra",
    "StatusRegra",
    "REGRAS_B3",
    "PENDENCIAS_GENIAL",
    "TODAS",
    "pendentes",
    "regra",
    "pagina",
    "bloco_boleta",
    "bloco_para_copiar",
    "painel_resumo",
    "secao_condicoes",
    "secao_pendencias",
    "faixa_nao_envia",
    "resumo_uma_linha",
    "SELO",
]
