"""Noticias e eventos: a agenda de risco, sem inventar manchete.

    from cashinho.core.noticias import AvaliadorDeEventos, FonteArquivo

    avaliador = AvaliadorDeEventos(FonteArquivo("eventos.json"))
    OpportunityEngine(eventos=avaliador)

O modulo identifica situacoes de risco - resultados, fatos relevantes, juros,
inflacao, payroll e eventos corporativos - e gera dado estruturado. Uma
notícia isolada **nunca** vira compra ou venda: ela so desconta score, reduz
posicao ou bloqueia a operacao.
"""

from .fontes import (
    VALIDADE_PADRAO_MIN,
    FonteArquivo,
    FonteComposta,
    FonteDeEventos,
    FonteEmMemoria,
    SemFonte,
    evento_de_dict,
)
from .modelos import AgendaDeEventos, Evento, EventoInvalidoError, agenda_indisponivel
from .politica import (
    JANELAS_PADRAO,
    PENALIDADE_PADRAO,
    RISCO_PADRAO,
    AvaliacaoDeEventos,
    AvaliadorDeEventos,
    ConfigEventos,
    JanelaDeProtecao,
    PoliticaDeEventos,
    risco_ajustado,
)
from .tipos import Disponibilidade, Severidade, TipoDeEvento, ViesDirecional
from .view import (
    cabecalho_disponibilidade,
    linha_do_evento,
    pagina,
    secao_noticias,
)

__all__ = [
    "Evento", "AgendaDeEventos", "EventoInvalidoError", "agenda_indisponivel",
    "TipoDeEvento", "Severidade", "ViesDirecional", "Disponibilidade",
    "FonteDeEventos", "FonteArquivo", "FonteEmMemoria", "FonteComposta", "SemFonte",
    "evento_de_dict", "VALIDADE_PADRAO_MIN",
    "PoliticaDeEventos", "AvaliadorDeEventos", "AvaliacaoDeEventos", "ConfigEventos",
    "JanelaDeProtecao", "JANELAS_PADRAO", "PENALIDADE_PADRAO", "RISCO_PADRAO",
    "risco_ajustado",
    "secao_noticias", "linha_do_evento", "cabecalho_disponibilidade", "pagina",
]
