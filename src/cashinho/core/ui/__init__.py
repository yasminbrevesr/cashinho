"""Peças de tela compartilhadas: cores, formatadores e parsers de CLI.

    from ..ui import c, num, pct, barra

Este modulo nao desenha tela nenhuma - ele existe para que as dezoito telas
que desenham nao precisem cada uma da sua copia de como pintar um texto.
"""

from .argumentos import data, hora as parse_hora, instante, percentuais
from .cores import PALETA, RESET, c, largura_visivel, sem_cor
from .formato import barra, barra_de_nota, formata_dinheiro, hora, num, ou_traco, pct

__all__ = [
    "c", "PALETA", "RESET", "sem_cor", "largura_visivel",
    "num", "pct", "hora", "barra", "barra_de_nota", "formata_dinheiro", "ou_traco",
    "data", "instante", "parse_hora", "percentuais",
]
