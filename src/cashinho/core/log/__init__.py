"""Log estruturado: JSONL, um arquivo por pregao, ligado ao System Health.

    from cashinho.core.log import Registrador, Nivel

    log = Registrador(pasta="logs", telemetria=monitor.telemetria)
    log.aviso("market_data", "fonte lenta", latencia_ms=3200)

Antes deste modulo, um erro so existia se alguem estivesse olhando na hora: a
divergencia entre risco e corretora virava string numa lista em memoria que
ninguem lia. Agora ela vai para o arquivo **e** para o painel de saude.
"""

from .modelos import EventoDeLog
from .niveis import Nivel, nivel_de
from .registrador import (
    MEMORIA_PADRAO,
    PASTA_PADRAO,
    Registrador,
    RegistradorNulo,
    ler,
)
from .view import linha, pagina

__all__ = [
    "Registrador", "RegistradorNulo", "Nivel", "nivel_de", "EventoDeLog",
    "ler", "pagina", "linha", "PASTA_PADRAO", "MEMORIA_PADRAO",
]
