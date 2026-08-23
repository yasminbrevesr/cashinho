"""Validacao de estrategias: protecao contra overfitting.

    from cashinho.core.validacao import DivisaoDeDados, ValidadorDeEstrategia

    divisao = DivisaoDeDados.por_percentual(serie, 0.6, 0.2, 0.2)
    relatorio = ValidadorDeEstrategia(EstrategiaOportunidade).validar(divisao)
    print(pagina(relatorio))

O TEST fica atras de um cofre: a selecao de parametros nao o recebe, e abri-lo
exige um motivo que fica registrado no relatorio.
"""

from .cofre import Abertura, CofreDeTeste, TesteProtegidoError, garantir_sem_teste
from .divisao import (
    DivisaoDeDados,
    DivisaoInvalidaError,
    Janela,
    Particao,
    dias_da_serie,
)
from .relatorio import (
    Alerta,
    CriteriosDeDegradacao,
    Medidas,
    RelatorioDeValidacao,
    Severidade,
)
from .selecao import (
    LIMITE_DE_CANDIDATOS,
    Candidato,
    CriteriosDeSelecao,
    GradeGrandeDemaisError,
    Medida,
    Selecao,
    SelecionadorEmTreino,
)
from .validador import ConfigValidacao, ValidadorDeEstrategia
from .view import (
    pagina,
    pagina_walk_forward,
    secao_alertas,
    secao_cofre,
    secao_selecao,
    tabela_particoes,
)
from .walkforward import (
    Ciclo,
    ConfigWalkForward,
    ResultadoWalkForward,
    janelas_walk_forward,
    walk_forward,
)

__all__ = [
    "DivisaoDeDados", "Particao", "Janela", "DivisaoInvalidaError", "dias_da_serie",
    "CofreDeTeste", "TesteProtegidoError", "garantir_sem_teste", "Abertura",
    "Candidato", "SelecionadorEmTreino", "Selecao", "Medida", "CriteriosDeSelecao",
    "GradeGrandeDemaisError", "LIMITE_DE_CANDIDATOS",
    "ValidadorDeEstrategia", "ConfigValidacao",
    "RelatorioDeValidacao", "Medidas", "Alerta", "Severidade", "CriteriosDeDegradacao",
    "walk_forward", "ConfigWalkForward", "ResultadoWalkForward", "Ciclo",
    "janelas_walk_forward",
    "pagina", "pagina_walk_forward", "tabela_particoes", "secao_alertas",
    "secao_cofre", "secao_selecao",
]
