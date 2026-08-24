"""A tela do log - as ultimas linhas, filtradas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from ..ui import c, hora
from .modelos import EventoDeLog
from .niveis import Nivel

LARGURA = 92


def linha(evento: EventoDeLog, referencia: Optional[datetime] = None,
          cores: bool = False) -> str:
    marca = c(f"{evento.nivel.simbolo} {evento.nivel.rotulo:<6}",
              evento.nivel.cor, ativo=cores and bool(evento.nivel.cor))
    dados = ""
    if evento.dados:
        dados = "  " + c(
            " ".join(f"{k}={v}" for k, v in list(evento.dados.items())[:4]),
            "cinza", ativo=cores)
    return (f"  {hora(evento.ts, referencia, segundos=True):<9}{marca}"
            f"{evento.componente:<15}{evento.mensagem}{dados}")


def pagina(eventos: Sequence[EventoDeLog], registrador=None, limite: int = 40,
           cores: bool = False, descartadas: Sequence[str] = ()) -> str:
    agora = datetime.now().astimezone()
    linhas = ["", c("LOG", "negrito", ativo=cores), "─" * LARGURA]

    if registrador is not None:
        estado = ("gravando" if registrador.gravando else
                  ("so em memoria" if registrador.pasta is None else "COM FALHA"))
        arquivo = registrador.arquivo_do_dia()
        linhas.append(f"  {estado}" + (f" · {arquivo}" if arquivo else ""))
        if registrador.falhas_de_escrita:
            linhas.append("  " + c(
                f"✖ {registrador.falhas_de_escrita} falha(s) de escrita: "
                f"{registrador.motivo_da_falha}", "vermelho", ativo=cores))
        linhas.append("")

    if not eventos:
        linhas.append("  nenhum evento no filtro pedido")
    else:
        por_nivel: dict[str, int] = {}
        for e in eventos:
            por_nivel[e.nivel.rotulo] = por_nivel.get(e.nivel.rotulo, 0) + 1
        resumo = " · ".join(f"{n} {q}" for n, q in sorted(por_nivel.items()))
        linhas.append(f"  {len(eventos)} evento(s): {resumo}")
        linhas.append("")
        for e in list(eventos)[:limite]:
            linhas.append(linha(e, agora, cores))
        if len(eventos) > limite:
            linhas.append(f"  ... e mais {len(eventos) - limite}")

    if descartadas:
        linhas.append("")
        linhas.append(f"  {len(descartadas)} linha(s) ilegivel(is) no arquivo:")
        for d in list(descartadas)[:3]:
            linhas.append(f"    · {d}")

    linhas.append("")
    return "\n".join(linhas)
