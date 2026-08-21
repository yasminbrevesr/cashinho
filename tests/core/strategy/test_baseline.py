"""A estrategia baseline: cada estado, cada filtro, e a reprodutibilidade."""

from __future__ import annotations

import pytest

from cashinho.core.strategy import (
    Action,
    BaselineConfig,
    BaselineTendenciaVolumeATR,
    StrategyContext,
)
from cashinho.models import Direction

from .factories import (
    serie_alta,
    serie_baixa,
    serie_de_closes,
    serie_embaralhada,
    serie_explosiva,
    serie_parada,
)


def avaliar(serie, config: BaselineConfig | None = None):
    return BaselineTendenciaVolumeATR(config).avaliar(StrategyContext("PETR4", serie))


# --- os quatro estados ----------------------------------------------------------


def test_tendencia_de_alta_com_tudo_no_lugar_gera_buy():
    s = avaliar(serie_alta())

    assert s.action is Action.BUY
    assert s.vies is Direction.LONG
    assert s.confidence >= 0.6
    assert s.contrarios == () or all(not f.obrigatorio for f in s.contrarios)


def test_tendencia_de_baixa_com_tudo_no_lugar_gera_sell():
    s = avaliar(serie_baixa())

    assert s.action is Action.SELL
    assert s.vies is Direction.SHORT
    assert "baixa" in s.setup


def test_medias_embaralhadas_geram_none():
    s = avaliar(serie_embaralhada())

    assert s.action is Action.NONE
    assert s.vies is None
    assert s.confidence == 0.0
    assert "sem tendencia definida" in s.reasons[0]


def test_volume_fraco_segura_o_sinal_em_wait():
    s = avaliar(serie_alta(volume_final=1.0))

    assert s.action is Action.WAIT
    assert s.vies is Direction.LONG  # o vies continua existindo
    assert [f.nome for f in s.faltando] == ["volume"]
    assert any("falta para acionar" in r for r in s.reasons)


def test_preco_do_lado_errado_da_media_curta_segura_em_wait():
    """Tendencia de alta, mas o candle fechou abaixo da EMA9."""
    closes = [30.0 * 1.001 ** i for i in range(80)]
    closes.append(closes[-1] * 0.99)  # um candle forte para baixo
    serie = serie_de_closes(closes, [10_000.0] * 80 + [30_000.0])

    s = avaliar(serie)
    assert s.action is Action.WAIT
    assert "preco x media de 9" in [f.nome for f in s.faltando]


# --- filtros que impedem qualquer leitura ------------------------------------------


def test_ativo_parado_e_descartado_pelo_atr():
    s = avaliar(serie_parada())

    assert s.action is Action.NONE
    assert "parado" in s.reasons[0]
    assert s.factors[0].nome == "volatilidade (ATR)"


def test_volatilidade_excessiva_tambem_e_descartada():
    s = avaliar(serie_explosiva())

    assert s.action is Action.NONE
    assert "excessiva" in s.reasons[0]


def test_candles_insuficientes_geram_none():
    s = avaliar(serie_alta(n=20))

    assert s.action is Action.NONE
    assert "insuficientes" in s.reasons[0]
    assert s.confidence == 0.0


def test_faixa_de_atr_e_configuravel():
    parada = serie_parada()
    padrao = avaliar(parada)
    assert padrao.action is Action.NONE
    assert "parado" in padrao.reasons[0]

    # com a faixa afrouxada o ATR deixa de ser o motivo do descarte
    frouxa = avaliar(parada, BaselineConfig(atr_min_pct=0.01))
    fator_atr = next(f for f in frouxa.factors if f.nome == "volatilidade (ATR)")
    assert fator_atr.favoravel is True
    assert "parado" not in frouxa.reasons[0]


def test_confianca_minima_alta_derruba_para_wait():
    exigente = BaselineConfig(confianca_minima=0.99)
    s = avaliar(serie_alta(), exigente)

    assert s.action is Action.WAIT
    assert any("confianca" in r for r in s.reasons)


def test_volume_minimo_e_configuravel():
    serie = serie_alta(volume_final=1.5)
    assert avaliar(serie, BaselineConfig(volume_minimo=1.2)).action is Action.BUY
    assert avaliar(serie, BaselineConfig(volume_minimo=2.0)).action is Action.WAIT


# --- conteudo do sinal ---------------------------------------------------------------


def test_sinal_lista_fatores_dos_dois_lados():
    s = avaliar(serie_alta())
    nomes = {f.nome for f in s.factors}

    assert {"empilhamento das medias", "inclinacao da media de 21", "preco x media de 9",
            "volume", "volatilidade (ATR)"} <= nomes
    assert all(f.detalhe for f in s.factors)  # todo fator explica o proprio numero


def test_fatores_obrigatorios_sao_os_cinco_pilares():
    s = avaliar(serie_alta())
    obrigatorios = {f.nome for f in s.factors if f.obrigatorio}

    assert obrigatorios == {
        "empilhamento das medias",
        "inclinacao da media de 21",
        "preco x media de 9",
        "volume",
        "volatilidade (ATR)",
    }


def test_invalidacao_aponta_um_nivel_concreto():
    s = avaliar(serie_alta())

    assert "EMA21" in s.invalidation
    assert "R$" in s.invalidation
    assert "desempilharem" in s.invalidation


def test_niveis_sao_referencia_e_ficam_do_lado_certo():
    compra = avaliar(serie_alta())
    venda = avaliar(serie_baixa())

    assert compra.niveis["stop_referencia"] < compra.niveis["entrada_referencia"]
    assert compra.niveis["alvo_referencia"] > compra.niveis["entrada_referencia"]
    assert venda.niveis["stop_referencia"] > venda.niveis["entrada_referencia"]
    assert venda.niveis["alvo_referencia"] < venda.niveis["entrada_referencia"]


def test_timestamp_do_sinal_e_o_do_ultimo_candle_fechado():
    serie = serie_alta()
    s = avaliar(serie)

    assert s.timestamp == serie.last.ts
    assert s.timeframe == serie.timeframe


def test_sinal_avisa_que_a_estrategia_e_de_validacao():
    s = avaliar(serie_alta())

    assert s.experimental is True
    assert "validacao" in s.aviso
    assert "nao e' uma estrategia final" in s.aviso


# --- reprodutibilidade e escopo --------------------------------------------------------


def test_mesma_serie_gera_exatamente_o_mesmo_sinal():
    serie = serie_alta()
    a = avaliar(serie)
    b = avaliar(serie)

    assert a.para_dict() == b.para_dict()


def test_avaliar_nao_altera_a_serie():
    serie = serie_alta()
    antes = [(c.ts, c.close, c.volume) for c in serie.candles]

    avaliar(serie)

    assert [(c.ts, c.close, c.volume) for c in serie.candles] == antes


def test_a_estrategia_nao_tem_como_enviar_ordem():
    metodos = {m for m in dir(BaselineTendenciaVolumeATR) if not m.startswith("_")}
    proibidos = {"executar", "enviar", "comprar", "vender", "ordem", "boleta", "abrir"}

    assert not (metodos & proibidos)
    assert metodos & {"avaliar"}


def test_contexto_vazio_e_recusado():
    from cashinho.models import Series

    with pytest.raises(ValueError, match="sem candles"):
        StrategyContext("PETR4", Series("PETR4", "5m", []))
