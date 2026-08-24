"""Telas de market data: origem, estado e qualidade do dado - sempre juntos.

Regra desta tela: **o usuario nunca precisa adivinhar de onde veio o numero
nem quando ele foi apurado.** Fonte, horario, idade e status aparecem coladas
no preco, e dado atrasado carrega o aviso em letra grande.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from ..core.ui import c, hora, num
from .cotacao import Cotacao
from .qualidade import Qualidade
from .servico import Leitura, MarketDataService
from .status import Capacidades, StatusDados

LARGURA = 72

_COR_DO_STATUS = {
    StatusDados.ONLINE: "verde",
    StatusDados.DELAYED: "amarelo",
    StatusDados.STALE: "vermelho",
    StatusDados.DEGRADED: "amarelo",
    StatusDados.OFFLINE: "vermelho",
}


def faixa_de_status(status: StatusDados, cores: bool = False) -> str:
    """A faixa que impede alguem de ler dado atrasado como cotacao do momento."""
    if not status.aviso:
        return ""
    estilo = ("vermelho", "negrito") if status is not StatusDados.DELAYED else ("amarelo", "negrito")
    linhas = ["╔" + "═" * (LARGURA - 2) + "╗",
              "║" + status.aviso.center(LARGURA - 2) + "║",
              "╚" + "═" * (LARGURA - 2) + "╝"]
    return "\n".join(c(l, *estilo, ativo=cores) for l in linhas)


def secao_fonte(fonte: str, status: StatusDados, momento: Optional[datetime],
                idade: str = "", cores: bool = False) -> str:
    linhas = [
        c(" ORIGEM DO DADO", "negrito", ativo=cores),
        f"   fonte         {fonte}",
        f"   status        " + c(status.value, _COR_DO_STATUS[status], ativo=cores)
        + f"  ({status.descricao})",
        f"   atualizacao   {hora(momento, segundos=True) if momento else '-'}"
        + (f"  ·  idade {idade}" if idade else ""),
    ]
    return "\n".join(linhas)


def secao_qualidade(q: Qualidade, cores: bool = False) -> str:
    cor = "verde" if q.valida and not q.avisos else ("amarelo" if q.valida else "vermelho")
    linhas = [c(" QUALIDADE DOS DADOS", "negrito", ativo=cores),
              f"   {c(q.rotulo, cor, ativo=cores)}  ·  {q.candles} candle(s)"]
    for p in q.problemas:
        linhas.append(f"   {p.gravidade.simbolo} {p.mensagem}")
    return "\n".join(linhas)


def pagina_analise(leitura: Leitura, cotacao: Optional[Cotacao] = None,
                   cores: bool = False) -> str:
    """A tela ANALISE pedida: ativo, provider, status, candles, qualidade."""
    serie = leitura.serie
    partes = ["", c(f"ANALISE · {serie.symbol} · {serie.timeframe}", "negrito", ativo=cores),
              "─" * LARGURA]

    faixa = faixa_de_status(leitura.status, cores)
    if faixa:
        partes.append(faixa)

    idade = cotacao.idade_legivel if cotacao else ""
    momento = serie.candles[-1].ts if len(serie) else None
    partes.append("")
    partes.append(secao_fonte(leitura.fonte, leitura.status, momento, idade, cores))

    partes.append("")
    partes.append(c(" DADOS", "negrito", ativo=cores))
    partes.append(f"   finalidade    {leitura.finalidade.rotulo}")
    partes.append(f"   candles       {len(serie)}")
    if len(serie):
        primeiro, ultimo = serie.candles[0], serie.candles[-1]
        partes.append(f"   periodo       {primeiro.ts:%d/%m %H:%M} a {ultimo.ts:%d/%m %H:%M}")
        partes.append(f"   ultimo preco  {num(ultimo.close)}")

    if cotacao is not None:
        partes.append("")
        partes.append(c(" COTACAO", "negrito", ativo=cores))
        partes.append(f"   ultimo {num(cotacao.last)}   abertura {num(cotacao.open)}"
                      f"   maxima {num(cotacao.high)}   minima {num(cotacao.low)}")
        partes.append(f"   fechamento anterior {num(cotacao.previous_close)}"
                      f"   volume {num(cotacao.volume, casas=0)}")
        if cotacao.bid is None and cotacao.ask is None:
            partes.append("   book          nao fornecido por esta fonte")

    partes.append("")
    partes.append(secao_qualidade(leitura.qualidade, cores))

    partes.append("")
    if leitura.utilizavel:
        partes.append(c(f"   dado adequado para {leitura.finalidade.rotulo.lower()}",
                        "verde", ativo=cores))
    else:
        partes.append(c(f"   NAO usar para {leitura.finalidade.rotulo.lower()}: "
                        f"{leitura.aviso}", "vermelho", "negrito", ativo=cores))
    partes.append("")
    return "\n".join(partes)


def secao_providers(servico: MarketDataService, cores: bool = False) -> str:
    """A secao MARKET DATA do System Health."""
    dados = servico.para_dict()
    linhas = [c(" MARKET DATA", "negrito", ativo=cores)]

    rotulo_largura = 24
    for papel, chave in (("Historical Provider", "historico"),
                         ("Realtime Provider", "tempo_real")):
        info = dados[chave]
        if info is None:
            linhas.append(f"   {papel:<{rotulo_largura}}"
                          + c("NAO CONFIGURADO", "cinza", ativo=cores))
            continue
        cap = info["capacidades"]
        atraso = cap["atraso_tipico_s"]
        detalhe = ("atraso declarado nao informado" if atraso is None
                   else f"atraso tipico {atraso / 60:.0f} min" if atraso >= 60
                   else f"atraso tipico {atraso:.0f} s")
        linhas.append(f"   {papel:<{rotulo_largura}}{info['nome']}  ·  {detalhe}")

    disponivel = dados["analise_em_tempo_real"] == "DISPONIVEL"
    linhas.append(f"   {'Analise em tempo real':<{rotulo_largura}}"
                  + c(dados["analise_em_tempo_real"],
                      "verde" if disponivel else "vermelho", ativo=cores))
    if not disponivel:
        linhas.append("   " + c("   novas oportunidades intradiarias bloqueadas",
                                "vermelho", ativo=cores))
    return "\n".join(linhas)
