"""Look-ahead: durante o replay, nenhum componente pode ver o futuro.

Estes sao os testes que sustentam o modulo. Se um deles cair, o replay esta
mentindo - e um replay que mente e' pior do que replay nenhum, porque da
confianca em cima de resultado impossivel.
"""

from __future__ import annotations

from datetime import date

import pytest

from cashinho.core.mtf import LookaheadError
from cashinho.core.replay import FitaDeMercado, MarketReplay, ReplayConfig, Velocidade
from cashinho.core.strategy.base import Strategy
from cashinho.core.strategy.context import StrategyContext
from cashinho.core.strategy.models import Action, Signal

from .factories import ABERTURA, DIA, pregao, replay, serie, serie_alta


# --- a fita nao entrega o futuro ------------------------------------------------


def test_pedir_candle_a_frente_levanta_lookahead():
    fita = FitaDeMercado(serie_alta(n=50))
    fita.avancar()
    fita.avancar()

    with pytest.raises(LookaheadError, match="ainda nao aconteceu"):
        fita.candle(5)
    with pytest.raises(LookaheadError):
        fita[10]


def test_a_fita_nao_tem_metodo_para_ver_o_futuro():
    metodos = {m for m in dir(FitaDeMercado) if not m.startswith("_")}
    proibidos = {"futuro", "proximo", "espiar", "todos", "serie_completa", "adiante"}

    assert not (metodos & proibidos)


def test_visivel_nunca_passa_do_instante_atual():
    fita = FitaDeMercado(serie_alta(n=80))
    for _ in range(30):
        fita.avancar()

    visivel = fita.visivel()
    assert len(visivel) == 30  # avancar() 30x a partir de -1 para no indice 29
    assert all(c.ts <= fita.instante for c in visivel)


def test_percorrer_a_fita_so_devolve_o_passado():
    fita = FitaDeMercado(serie_alta(n=40))
    for _ in range(10):
        fita.avancar()

    assert len(list(fita)) == 10
    assert all(c.ts <= fita.instante for c in fita)


def test_a_fita_antes_de_comecar_nao_tem_candle_atual():
    fita = FitaDeMercado(serie_alta(n=10))

    assert fita.comecou is False
    with pytest.raises(LookaheadError):
        fita.atual


def test_restantes_conta_sem_revelar_preco():
    fita = FitaDeMercado(serie_alta(n=50))
    fita.avancar()

    assert fita.restantes == 49
    assert fita.total == 50  # contagem e' permitida; preco, nao


# --- a estrategia so ve o que ja fechou ---------------------------------------------


class EstrategiaEspia(Strategy):
    """Anota tudo o que viu, para o teste conferir depois."""

    nome = "espia-replay"
    experimental = False

    def __init__(self):
        self.visto: list[tuple] = []

    def avaliar(self, contexto: StrategyContext) -> Signal:
        serie = contexto.serie
        vista = contexto.extras.get("vista")
        self.visto.append((
            contexto.timestamp,
            serie.last.ts if len(serie) else None,
            max((c.ts for c in serie.candles), default=None),
            vista.instante if vista is not None else None,
        ))
        return self.sinal_vazio(contexto, "espiando")


def test_a_estrategia_nunca_recebe_candle_do_futuro():
    espia = EstrategiaEspia()
    r = MarketReplay(serie_alta(n=200), ReplayConfig(symbol="PETR4",
                                                     velocidade=Velocidade.MAXIMA,
                                                     minimo_para_analisar=30),
                     estrategia=espia)
    r.executar()

    assert espia.visto
    for timestamp, ultimo, maximo, instante in espia.visto:
        assert instante is not None
        assert ultimo <= instante, "a estrategia recebeu candle nao fechado"
        assert maximo <= instante, "havia candle do futuro na serie entregue"


def test_a_serie_entregue_cresce_um_candle_por_vez():
    espia = EstrategiaEspia()
    r = MarketReplay(serie_alta(n=120), ReplayConfig(symbol="PETR4",
                                                     minimo_para_analisar=30),
                     estrategia=espia)
    r.executar()

    instantes = [v[3] for v in espia.visto]
    assert instantes == sorted(instantes)
    assert len(set(instantes)) == len(instantes)  # um instante por passo


# --- as camadas multi-timeframe -------------------------------------------------------


def test_nenhuma_camada_usa_barra_que_ainda_nao_fechou():
    r, _ = pregao()
    verificadas = 0
    for passo in r:
        if passo.resultado is None or passo.resultado.opportunity is None:
            continue
        leitura = passo.resultado.opportunity.leitura
        if leitura is None:
            continue
        for camada in leitura.camadas:
            assert camada.fechado_em <= passo.instante, (
                f"{camada.papel} usou barra que fecha em {camada.fechado_em}"
            )
            verificadas += 1
    assert verificadas > 0


def test_todo_sinal_carimba_o_instante_do_replay():
    r, _ = pregao()
    for passo in r:
        if passo.resultado and passo.resultado.signal:
            assert passo.resultado.signal.timestamp <= passo.instante


# --- o teste decisivo -------------------------------------------------------------------


def test_o_replay_decide_igual_a_um_engine_que_so_conhece_o_passado():
    """A prova: recortar a serie no instante N e reprocessar da o mesmo resultado.

    Se qualquer componente estivesse espiando adiante, o replay - que carrega
    a serie inteira na memoria - decidiria diferente de um engine que so
    recebeu os candles ate N.
    """
    from cashinho.models import Series
    from cashinho.core.oportunidade import OpportunityEngine

    r, _ = pregao()
    do_dia = r.fita._serie          # a serie do pregao que o replay recebeu
    passos = list(r)

    conferidos = 0
    for passo in passos[120::60]:
        do_replay = passo.resultado.opportunity if passo.resultado else None
        if do_replay is None or do_replay.entry == 0:
            continue

        # um engine limpo, com a serie truncada exatamente naquele candle
        truncada = Series(do_dia.symbol, do_dia.timeframe,
                          do_dia.candles[: passo.indice + 1])
        engine = OpportunityEngine()
        vista = engine.alimentar(truncada).em(passo.instante)
        sozinho = engine.avaliar(vista, do_dia.symbol)

        assert sozinho.estado is do_replay.estado
        assert sozinho.score == pytest.approx(do_replay.score, abs=0.05)
        assert sozinho.entry == pytest.approx(do_replay.entry, abs=1e-6)
        conferidos += 1

    assert conferidos > 0, "nenhum ponto comparavel - o teste nao provou nada"


# --- a corretora ---------------------------------------------------------------------------


def test_a_corretora_recebe_um_candle_por_vez_e_sempre_o_atual():
    r = replay(serie_alta(n=120))
    recebidos: list = []
    original = r.broker.processar

    def espiao(symbol, candle):
        recebidos.append(candle)
        return original(symbol, candle)

    r.broker.processar = espiao
    r.executar()

    assert len(recebidos) == r.estado.passos
    for i, candle in enumerate(recebidos):
        assert candle is r.fita.candle(i)  # exatamente o candle daquele passo


def test_o_paper_broker_nunca_recebe_a_serie_inteira():
    import inspect

    from cashinho.core.replay import replay as modulo

    fonte = inspect.getsource(modulo.MarketReplay.passo)
    assert "fita.visivel()" not in fonte
    assert "processar(self.config.symbol, candle)" in fonte
