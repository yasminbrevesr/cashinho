"""Eventos de estrutura: rompimento, possivel falso rompimento e pullback.

Definicoes objetivas:

- **rompimento**: o candle FECHA alem da zona por pelo menos
  ``rompimento_min_atr`` ATR, e a zona ja existia antes desse candle;
- **possivel falso rompimento**: (a) rompeu e voltou para dentro da zona em
  ate ``falso_rompimento_janela`` candles, ou (b) a maxima furou a zona mas o
  candle fechou de volta - a classica rejeicao. E' "possivel" de proposito:
  so o proximo candle confirma;
- **pullback**: correcao contra a tendencia dentro da perna valida, entre
  ``pullback_min`` e ``pullback_max`` de retracao, sem violar a origem.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ...models import Direction, Series, formata_dinheiro
from ...indicators.volume import volume_relativo
from .config import PADRAO, EstruturaConfig
from .models import EventoEstrutura, Level, Regime, Swing, Tendencia, TipoEvento


def detecta_eventos(
    serie: Series,
    niveis: Sequence[Level],
    tendencia: Tendencia,
    swing_valido: Optional[Swing],
    atr: float,
    cfg: EstruturaConfig = PADRAO,
) -> list[EventoEstrutura]:
    """Varre a janela recente e devolve os eventos em ordem cronologica."""
    candles = serie.candles
    n = len(candles)
    if n == 0 or atr <= 0:
        return []

    eventos: list[EventoEstrutura] = []
    vrel = volume_relativo(serie.volumes, 20)
    margem = atr * cfg.rompimento_min_atr
    inicio = max(n - cfg.janela_eventos, 0)

    for nivel in niveis:
        evento = _evento_de_nivel(candles, nivel, inicio, n, margem, atr, vrel, cfg)
        if evento:
            eventos.append(evento)

    pb = _pullback(serie, tendencia, swing_valido, atr, cfg)
    if pb:
        eventos.append(pb)

    eventos.sort(key=lambda e: (e.indice, e.tipo.value))
    return eventos


def _evento_de_nivel(candles, nivel: Level, inicio: int, n: int, margem: float,
                     atr: float, vrel, cfg: EstruturaConfig) -> Optional[EventoEstrutura]:
    """Ultimo rompimento (ou rejeicao) daquele nivel dentro da janela.

    Rompimento e' CRUZAMENTO: o candle fecha alem da zona vindo do outro lado.
    Sem essa exigencia, um suporte 3 ATR abaixo do preco seria "rompido" a
    cada candle, so por estar abaixo.
    """
    formado_ate = (max(nivel.pivos) + cfg.pivo_direita) if nivel.pivos else -1
    primeiro = max(inicio, formado_ate + 1, 1)

    cruzamentos: list[tuple[int, Direction]] = []
    for j in range(primeiro, n):
        anterior = candles[j - 1].close
        atual = candles[j].close
        if atual > nivel.high + margem and anterior <= nivel.high + margem:
            cruzamentos.append((j, Direction.LONG))
        elif atual < nivel.low - margem and anterior >= nivel.low - margem:
            cruzamentos.append((j, Direction.SHORT))

    if cruzamentos:
        j, direcao = cruzamentos[-1]
        if len(cruzamentos) >= 2:
            j_anterior, direcao_anterior = cruzamentos[-2]
            voltou_rapido = (j - j_anterior) <= cfg.falso_rompimento_janela
            if voltou_rapido and direcao_anterior is not direcao:
                return EventoEstrutura(
                    tipo=TipoEvento.POSSIVEL_FALSO_ROMPIMENTO,
                    direcao=direcao,
                    ts=candles[j].ts,
                    indice=j,
                    preco=candles[j].close,
                    forca=_forca_falso(candles, j_anterior, j, nivel, atr, vrel),
                    descricao=(
                        f"rompeu {'acima' if direcao_anterior is Direction.LONG else 'abaixo'} de "
                        f"{formata_dinheiro(nivel.high if direcao_anterior is Direction.LONG else nivel.low)} "
                        f"e voltou para dentro da zona em {j - j_anterior} candle(s) - "
                        f"possivel falso rompimento"
                    ),
                    nivel=nivel,
                    detalhes={"candle_rompimento": j_anterior, "candle_retorno": j},
                )
        return EventoEstrutura(
            tipo=TipoEvento.ROMPIMENTO,
            direcao=direcao,
            ts=candles[j].ts,
            indice=j,
            preco=candles[j].close,
            forca=_forca_rompimento(candles[j], nivel, direcao, atr, vrel[j] if j < len(vrel) else None),
            descricao=(
                f"fechou {'acima' if direcao is Direction.LONG else 'abaixo'} da zona "
                f"{formata_dinheiro(nivel.low)}-{formata_dinheiro(nivel.high)} "
                f"({nivel.toques} toque(s))"
            ),
            nivel=nivel,
            detalhes={"volume_relativo": round(vrel[j], 2) if j < len(vrel) and vrel[j] else None},
        )

    # sem cruzamento: procura rejeicao (a sombra furou, o candle fechou de volta)
    for j in range(n - 1, primeiro - 1, -1):
        c = candles[j]
        furou_acima = c.high > nivel.high + margem and c.close <= nivel.high
        furou_abaixo = c.low < nivel.low - margem and c.close >= nivel.low
        if not (furou_acima or furou_abaixo):
            continue
        tentativa = Direction.LONG if furou_acima else Direction.SHORT
        return EventoEstrutura(
            tipo=TipoEvento.POSSIVEL_FALSO_ROMPIMENTO,
            direcao=tentativa.oposta,
            ts=c.ts,
            indice=j,
            preco=c.close,
            forca=_forca_rejeicao(c, nivel, tentativa, atr),
            descricao=(
                f"sombra furou a zona {formata_dinheiro(nivel.low)}-{formata_dinheiro(nivel.high)} "
                f"mas o candle fechou de volta - rejeicao"
            ),
            nivel=nivel,
            detalhes={"tipo_rejeicao": "sombra"},
        )
    return None


def _forca_rompimento(candle, nivel: Level, direcao: Direction, atr: float, vrel) -> float:
    distancia = (candle.close - nivel.high) if direcao is Direction.LONG else (nivel.low - candle.close)
    forca = 0.35 * min(max(distancia, 0) / (atr * 0.5), 1.0)
    forca += 0.30 * min((vrel or 1.0) / 2.0, 1.0)
    forca += 0.20 * min(candle.body / atr, 1.0)
    forca += 0.15 * nivel.forca
    return round(max(0.0, min(1.0, forca)), 3)


def _forca_falso(candles, j: int, k: int, nivel: Level, atr: float, vrel) -> float:
    rapidez = 1.0 - (k - j - 1) / 3.0
    excursao = abs(candles[j].close - (nivel.high if candles[j].close > nivel.high else nivel.low))
    forca = 0.45 * max(rapidez, 0.0) + 0.25 * min(excursao / atr, 1.0) + 0.30 * nivel.forca
    return round(max(0.0, min(1.0, forca)), 3)


def _forca_rejeicao(candle, nivel: Level, direcao: Direction, atr: float) -> float:
    sombra = candle.upper_shadow if direcao is Direction.LONG else candle.lower_shadow
    proporcao = sombra / candle.range if candle.range else 0.0
    forca = 0.45 * proporcao + 0.25 * min(sombra / atr, 1.0) + 0.30 * nivel.forca
    return round(max(0.0, min(1.0, forca)), 3)


def _pullback(serie: Series, tendencia: Tendencia, swing: Optional[Swing], atr: float,
              cfg: EstruturaConfig) -> Optional[EventoEstrutura]:
    if swing is None or tendencia.regime is Regime.LATERAL:
        return None
    if swing.direcao is not tendencia.direcao:
        return None

    preco = serie.price
    retracao = swing.retracao_em(preco)
    if retracao is None or not (cfg.pullback_min <= retracao <= cfg.pullback_max):
        return None

    alta = swing.eh_alta
    origem = swing.inicio.preco
    if (alta and preco <= origem) or (not alta and preco >= origem):
        return None  # devolveu a perna inteira: nao e' mais pullback

    # a zona nobre (38,2% a 61,8%) vale mais que uma correcao rasa ou profunda
    distancia_do_centro = abs(retracao - 0.5)
    forca = 0.55 + 0.30 * max(0.0, 1.0 - distancia_do_centro / 0.28) + 0.15 * tendencia.forca
    ultimo = serie.last
    return EventoEstrutura(
        tipo=TipoEvento.PULLBACK,
        direcao=swing.direcao,
        ts=ultimo.ts,
        indice=len(serie) - 1,
        preco=preco,
        forca=round(max(0.0, min(1.0, forca)), 3),
        descricao=(
            f"corrigindo {retracao * 100:.1f}% da perna de "
            f"{'alta' if alta else 'baixa'} ({formata_dinheiro(swing.inicio.preco)} -> "
            f"{formata_dinheiro(swing.fim.preco)}), a favor da tendencia"
        ),
        detalhes={"retracao": round(retracao, 4), "amplitude_atr": swing.amplitude_atr},
    )
