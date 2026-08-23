"""Sincronizacao multi-timeframe: alinhamento de timestamps e nao vazamento.

Estes sao os testes que sustentam o engine. Se um deles cair, a leitura de
uma camada esta usando informacao que ainda nao existia.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.confluencia import MultiTimeframeEngine
from cashinho.core.confluencia.modelos import Camada, LeituraMultiTimeframe
from cashinho.core.confluencia.estados import ContextState
from cashinho.core.mtf import LookaheadError

from .factories import ABERTURA, motor, serie_alta, serie_parada, vista_em

ENGINE = MultiTimeframeEngine()


# ---------------------------------------------------------------------------
# o instante e' um so
# ---------------------------------------------------------------------------


def test_todas_as_camadas_sao_lidas_no_mesmo_instante():
    vista = vista_em(serie_alta(), 200)
    leitura = ENGINE.ler(vista, "PETR4")

    assert leitura.instante == vista.instante
    for c in leitura.camadas:
        assert c.lido_em == leitura.instante


def test_nenhuma_camada_usa_candle_que_ainda_nao_fechou():
    """A invariante central: fechado_em <= instante, camada por camada."""
    serie = serie_alta()
    m = motor(serie)

    verificadas = 0
    for vista in list(m.replay())[::17]:
        leitura = MultiTimeframeEngine().ler(vista, "PETR4")
        for c in leitura.camadas:
            assert c.fechado_em <= vista.instante, f"{c.papel} usou candle do futuro"
            assert c.ts < c.fechado_em  # abertura antes do fechamento
            verificadas += 1
    assert verificadas > 0


def test_camada_com_candle_do_futuro_e_recusada_na_construcao():
    """Nem construindo na mao: o modelo se recusa a existir."""
    t = ABERTURA + timedelta(hours=1)
    with pytest.raises(ValueError, match="ler o futuro"):
        Camada("context", "60m", ContextState.BULLISH, ts=t, fechado_em=t + timedelta(hours=1), lido_em=t)


def test_leitura_recusa_camadas_de_instantes_diferentes():
    t = ABERTURA + timedelta(hours=2)
    a = Camada("context", "60m", ContextState.BULLISH, ts=t - timedelta(hours=1),
               fechado_em=t, lido_em=t)
    b = Camada("trend", "15m", ContextState.BULLISH, ts=t - timedelta(minutes=15),
               fechado_em=t, lido_em=t + timedelta(minutes=1))

    with pytest.raises(ValueError, match="mesmo instante"):
        LeituraMultiTimeframe("PETR4", t, (a, b))


# ---------------------------------------------------------------------------
# cada camada anda no seu proprio relogio
# ---------------------------------------------------------------------------


def test_camada_maior_so_muda_quando_o_candle_dela_fecha():
    """Entre dois fechamentos de 60m, o contexto e' exatamente o mesmo."""
    serie = serie_alta()
    m = motor(serie)
    engine = MultiTimeframeEngine()

    leituras = {}
    for minuto in range(120, 175):  # atravessa varios candles de 1m e 5m
        vista = m.em(ABERTURA + timedelta(minutes=minuto))
        contexto = engine.ler(vista, "PETR4").camada("context")
        if contexto is None:
            continue
        leituras.setdefault(contexto.fechado_em, set()).add((contexto.valor, contexto.ts))

    for fechado_em, valores in leituras.items():
        assert len(valores) == 1, f"o contexto mudou sem candle novo de 60m em {fechado_em}"


def test_o_gatilho_muda_sem_arrastar_o_contexto():
    serie = serie_alta()
    m = motor(serie)
    engine = MultiTimeframeEngine()

    a = engine.ler(m.em(ABERTURA + timedelta(minutes=130)), "PETR4")
    b = engine.ler(m.em(ABERTURA + timedelta(minutes=131)), "PETR4")

    assert a.trigger.ts != b.trigger.ts  # o gatilho andou
    assert a.context.ts == b.context.ts  # o contexto nao
    assert a.context.fechado_em == b.context.fechado_em


def test_idade_de_cada_camada_reflete_o_proprio_timeframe():
    """As 11:37, o candle de 60m das 11:00 tem 37 min; o de 1m, zero."""
    serie = serie_alta()
    vista = motor(serie).em(ABERTURA + timedelta(minutes=97))  # 11:37
    leitura = MultiTimeframeEngine().ler(vista, "PETR4")

    assert leitura.context.idade_minutos == pytest.approx(37.0)
    assert leitura.trigger.idade_minutos == pytest.approx(0.0)
    assert leitura.context.idade_minutos > leitura.trend.idade_minutos
    assert leitura.trend.idade_minutos >= leitura.setup.idade_minutos


def test_camada_sem_candle_fechado_entra_em_faltando():
    """As 10:03 nao existe candle de 60m, 15m nem 5m fechado."""
    serie = serie_alta()
    vista = motor(serie).em(ABERTURA + timedelta(minutes=3))
    leitura = MultiTimeframeEngine().ler(vista, "PETR4")

    assert set(leitura.faltando) == {"context", "trend", "setup"}
    assert leitura.completa is False
    assert leitura.camada("trigger") is not None  # o 1m ja fechou


def test_camada_ausente_nao_vira_neutra_por_engano():
    """Faltar dado e' diferente de estar neutro - a regra nao pode confundir."""
    vista = motor(serie_alta()).em(ABERTURA + timedelta(minutes=3))
    resultado = MultiTimeframeEngine().avaliar(vista, "PETR4")

    assert "context" in resultado.leitura.faltando
    assert resultado.leitura.camada("context") is None
    assert resultado.oportunidade is None
    for a in resultado.avaliacoes:
        if a.regra.exigencias["context"]:
            assert not a.satisfeita


# ---------------------------------------------------------------------------
# leitura estavel e sem efeito colateral
# ---------------------------------------------------------------------------


def test_ler_o_mesmo_instante_duas_vezes_da_o_mesmo_resultado():
    vista = vista_em(serie_alta(), 250)
    engine = MultiTimeframeEngine()

    a = engine.ler(vista, "PETR4")
    b = engine.ler(vista, "PETR4")

    assert a.para_dict() == b.para_dict()


def test_engines_diferentes_leem_a_mesma_coisa():
    """O cache interno nao pode fazer duas instancias divergirem."""
    vista = vista_em(serie_alta(), 250)

    a = MultiTimeframeEngine().ler(vista, "PETR4")
    b = MultiTimeframeEngine().ler(vista, "PETR4")

    assert a.para_dict() == b.para_dict()


def test_ler_o_passado_depois_do_futuro_nao_contamina():
    """Ler as 12:00 e depois as 10:30 nao pode trazer nada das 12:00."""
    serie = serie_alta()
    m = motor(serie)
    engine = MultiTimeframeEngine()

    tarde = ABERTURA + timedelta(minutes=180)
    cedo = ABERTURA + timedelta(minutes=90)

    engine.ler(m.em(tarde), "PETR4")
    depois = engine.ler(m.em(cedo), "PETR4")
    limpo = MultiTimeframeEngine().ler(m.em(cedo), "PETR4")

    assert depois.para_dict() == limpo.para_dict()
    for c in depois.camadas:
        assert c.fechado_em <= cedo


def test_replay_inteiro_sem_vazamento():
    """Percorre o pregao candle a candle checando a invariante em todos."""
    serie = serie_alta(n=300)
    m = motor(serie)
    engine = MultiTimeframeEngine()

    instantes = 0
    for vista in m.replay():
        leitura = engine.ler(vista, "PETR4")
        instantes += 1
        for c in leitura.camadas:
            assert c.fechado_em <= vista.instante
            assert c.idade_minutos >= 0
    assert instantes == 300


def test_a_vista_continua_bloqueando_leitura_de_candle_em_formacao():
    """O engine nao contorna a protecao do motor de alinhamento."""
    vista = motor(serie_alta()).em(ABERTURA + timedelta(minutes=37))

    with pytest.raises(LookaheadError):
        vista.camada("context")  # 60m das 10:00 so fecha as 11:00


# ---------------------------------------------------------------------------
# configuracao
# ---------------------------------------------------------------------------


def test_combinacao_de_timeframes_e_configuravel():
    from cashinho.core.mtf import MTFConfig

    config = MTFConfig(base="1m", camadas={"context": "30m", "trend": "10m",
                                           "setup": "2m", "trigger": "1m"})
    engine = MultiTimeframeEngine(config)
    vista = motor(serie_alta(), engine).em(ABERTURA + timedelta(minutes=200))
    leitura = engine.ler(vista, "PETR4")

    assert [c.timeframe for c in leitura.camadas] == ["30m", "10m", "2m", "1m"]
    assert leitura.context.timeframe == "30m"


def test_papel_sem_leitor_e_recusado():
    from cashinho.core.mtf import MTFConfig, MTFError

    with pytest.raises(MTFError, match="sem leitor"):
        MultiTimeframeEngine(MTFConfig(base="1m", camadas={"macro": "60m", "trigger": "1m"}))
