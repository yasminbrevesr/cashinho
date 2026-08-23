"""System Health: o painel que diz se da para operar agora.

    from cashinho.core.saude import MonitorDeSaude, pagina

    monitor = MonitorDeSaude(risco=risco, broker=broker, noticias=agenda)
    print(pagina(monitor.verificar()))

Sete componentes, tres estados (ONLINE, DEGRADED, OFFLINE) e uma regra que
sai da tela e vira trava: **Market Data fora do ar ou desatualizado bloqueia
operacao nova** (ver ``BrokerComSaude``).
"""

from .estados import EstadoDeSaude, Modo, pior_de
from .guarda import BrokerComSaude, OperacaoBloqueadaPorSaudeError
from .modelos import COMPONENTES, NOMES, Componente, SaudeDoSistema
from .monitor import MARCO_ANALISE, ConfigSaude, MonitorDeSaude
from .sondas import (
    LimiaresSaude,
    Sonda,
    SondaBanco,
    SondaBroker,
    SondaMarketData,
    SondaNoticias,
    SondaPorTelemetria,
    SondaRisco,
)
from .telemetria import Anotacoes, RegistroDeErro, Telemetria
from .view import (
    faixa_de_operacao,
    linha_do_componente,
    linha_resumo,
    pagina,
    secao_erros,
)

__all__ = [
    "EstadoDeSaude", "Modo", "pior_de",
    "Componente", "SaudeDoSistema", "COMPONENTES", "NOMES",
    "MonitorDeSaude", "ConfigSaude", "MARCO_ANALISE",
    "Telemetria", "RegistroDeErro", "Anotacoes",
    "Sonda", "SondaMarketData", "SondaPorTelemetria", "SondaBanco", "SondaBroker",
    "SondaRisco", "SondaNoticias", "LimiaresSaude",
    "BrokerComSaude", "OperacaoBloqueadaPorSaudeError",
    "pagina", "linha_do_componente", "faixa_de_operacao", "secao_erros", "linha_resumo",
]
