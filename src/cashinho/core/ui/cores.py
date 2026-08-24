"""A paleta e o unico lugar que sabe escrever codigo ANSI.

Antes desta extracao, o mesmo dicionario de cores e a mesma funcao ``_c``
estavam copiados em **18** arquivos de view. Copia nao e' so feio: quando uma
tela ganhava uma cor nova (azul no replay, inverso no risco), as outras
dezessete nao ganhavam, e a diferenca so aparecia na tela.

Nada aqui decide *quando* colorir - isso e' de cada tela. Este arquivo so
sabe pintar.
"""

from __future__ import annotations

PALETA: dict[str, str] = {
    # basicas
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "azul": "\033[36m",
    "cinza": "\033[90m",
    # estilos
    "negrito": "\033[1m",
    "inverso": "\033[7m",
    "reset": "\033[0m",
    # apelidos semanticos: a tela de estrutura fala em alta/baixa, nao em
    # verde/vermelho, e esta e' a traducao - nao uma segunda paleta
    "alta": "\033[32m",
    "baixa": "\033[31m",
    "neutro": "\033[33m",
    "fraco": "\033[90m",
}

RESET = PALETA["reset"]


def c(texto: str, *estilos: str, ativo: bool = True) -> str:
    """Pinta o texto. Estilo desconhecido e' ignorado, nunca quebra a tela.

    ``ativo=False`` devolve o texto limpo - e' assim que ``--sem-cor`` e a
    saida para arquivo funcionam sem cada tela precisar de um ``if``.
    """
    if not ativo:
        return texto
    prefixo = "".join(PALETA[e] for e in estilos if e in PALETA)
    return f"{prefixo}{texto}{RESET}" if prefixo else texto


def sem_cor(texto: str) -> str:
    """Remove qualquer codigo ANSI - util para medir largura e para testes."""
    import re

    return re.sub(r"\033\[[0-9;]*m", "", texto)


def largura_visivel(texto: str) -> int:
    """Quantas colunas o texto ocupa, ignorando os codigos de cor."""
    return len(sem_cor(texto))
