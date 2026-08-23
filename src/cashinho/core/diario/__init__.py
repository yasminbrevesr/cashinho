"""Diario de Trades: registra, filtra e resume as operacoes.

    from cashinho.core.diario import BrokerComDiario, DiarioDeTrades, pagina

    broker = BrokerComDiario(paper_broker, DiarioDeTrades())
    broker.anotar_contexto("PETR4", oportunidade=op, auditoria=auditoria)
    ...                                   # opera normalmente
    print(pagina(broker.diario))          # as operacoes ja estao registradas

**Sem IA nesta etapa.** As estatisticas sao contagem, soma e divisao - nada
aqui sugere mudanca de estrategia nem ajusta parametro sozinho. O diario
mede; quem decide e' voce.
"""

from .diario import DiarioDeTrades
from .estatisticas import (
    AGRUPAMENTOS,
    AMOSTRA_MINIMA,
    Estatistica,
    agrupar,
    calcular,
    por_ativo,
    por_dia_da_semana,
    por_horario,
    por_setup,
    por_timeframe,
    todos_os_agrupamentos,
)
from .modelos import DIAS_DA_SEMANA, MOTIVOS_DE_SAIDA, Filtro, Registro
from .registrador import BrokerComDiario, ContextoDeEntrada
from .view import (
    detalhe_registro,
    pagina,
    painel_total,
    resumo,
    tabela_estatisticas,
    tabela_registros,
)

__all__ = [
    "DiarioDeTrades",
    "Registro",
    "Filtro",
    "BrokerComDiario",
    "ContextoDeEntrada",
    "Estatistica",
    "calcular",
    "agrupar",
    "por_setup",
    "por_ativo",
    "por_horario",
    "por_dia_da_semana",
    "por_timeframe",
    "todos_os_agrupamentos",
    "AGRUPAMENTOS",
    "AMOSTRA_MINIMA",
    "DIAS_DA_SEMANA",
    "MOTIVOS_DE_SAIDA",
    "pagina",
    "tabela_registros",
    "tabela_estatisticas",
    "painel_total",
    "detalhe_registro",
    "resumo",
]
