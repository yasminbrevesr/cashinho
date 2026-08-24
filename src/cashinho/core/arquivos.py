"""Escrita que nao deixa arquivo pela metade.

``write_text`` trunca o arquivo antes de escrever. Se o processo morrer no
meio - e' o caso mais provavel de morrer, porque e' quando ha I/O - o que fica
no disco e' um arquivo vazio ou cortado no meio de um JSON. O estado do Paper
Broker, o estado do risco e a configuracao sao gravados assim.

A troca e' escrever num temporario **na mesma pasta** e renomear por cima.
``os.replace`` e' atomico dentro do mesmo sistema de arquivos: ou o arquivo
antigo continua inteiro, ou o novo esta inteiro. Nunca metade dos dois.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


def escrever_texto(caminho: Path | str, conteudo: str, encoding: str = "utf-8",
                   fsync: bool = True) -> Path:
    """Grava o texto de forma atomica. Devolve o caminho.

    ``fsync=False`` mantem a **atomicidade** (ninguem ve arquivo pela metade) e
    abre mao da **durabilidade** (um desligamento pode perder a ultima
    gravacao). E' o certo para cache: pagar fsync a cada busca de candle e'
    caro, e cache perdido so custa buscar de novo.
    """
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # o temporario precisa ficar na MESMA pasta: os.replace so e' atomico
    # dentro do mesmo sistema de arquivos, e /tmp costuma ser outro
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.",
                                      suffix=".parcial")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(conteudo)
            fh.flush()
            if fsync:
                os.fsync(fh.fileno())  # sem isto, o rename pode chegar antes dos dados
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    return destino


def escrever_json(caminho: Path | str, dados: Any, indent: Optional[int] = 2,
                  fsync: bool = True) -> Path:
    """Grava JSON de forma atomica, no padrao do projeto (indentado, com acento)."""
    return escrever_texto(
        caminho,
        json.dumps(dados, indent=indent, ensure_ascii=False, default=str) + "\n",
        fsync=fsync)
