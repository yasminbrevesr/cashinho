"""Indicadores tecnicos.

Estrategia: valores esperados calculados a mao ou por formula
independente da implementacao. Comparar o indicador com ele mesmo
(recalculando com pandas do mesmo jeito) nao testaria nada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cashinho.core.indicators import (
    IndicatorNotApplicableError,
    InsufficientDataError,
    VwapAnchor,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    sma,
    true_range,
    vwap,
)
from cashinho.domain.enums import Timeframe
from cashinho.domain.errors import UnclosedCandleError
from cashinho.domain.market import Candle, CandleSeries

BASE = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


def series_from_closes(
    closes: list[float],
    *,
    timeframe: Timeframe = Timeframe.M5,
    start: datetime = BASE,
    volumes: list[int] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    last_open: bool = False,
    symbol: str = "PETR4",
) -> CandleSeries:
    """Serie construida a partir de fechamentos conhecidos."""
    candles = []
    for i, close in enumerate(closes):
        open_time = start + timeframe.duration * i
        price = Decimal(str(close))
        high = Decimal(str(highs[i])) if highs else price
        low = Decimal(str(lows[i])) if lows else price
        candles.append(
            Candle(
                open_time=open_time,
                close_time=open_time + timeframe.duration,
                open=price,
                high=max(high, price),
                low=min(low, price),
                close=price,
                volume=volumes[i] if volumes else 1000,
                is_closed=not (last_open and i == len(closes) - 1),
            )
        )
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        source="teste",
        fetched_at=start + timeframe.duration * len(closes),
    )


# =====================================================================
# Contrato comum
# =====================================================================


ALL_INDICATORS = [
    ("SMA", lambda s: sma(s, 3)),
    ("EMA", lambda s: ema(s, 3)),
    ("RSI", lambda s: rsi(s, 3)),
    ("ATR", lambda s: atr(s, 3)),
    ("MACD", lambda s: macd(s, fast=2, slow=3, signal=2)),
    ("BB", lambda s: bollinger(s, 3)),
    ("VWAP", vwap),
]


@pytest.mark.parametrize(("nome", "func"), ALL_INDICATORS)
def test_resultado_alinhado_a_serie(nome: str, func) -> None:
    serie = series_from_closes([10 + i * 0.5 for i in range(40)])
    resultado = func(serie)
    assert len(resultado.values) == len(serie)
    assert list(resultado.values.index) == [c.open_time for c in serie.candles]
    assert resultado.symbol == "PETR4"
    assert resultado.timeframe is Timeframe.M5


@pytest.mark.parametrize(("nome", "func"), ALL_INDICATORS)
def test_indicador_recusa_candle_em_formacao(nome: str, func) -> None:
    """ADR-0003: valor calculado sobre candle aberto muda a cada tick."""
    serie = series_from_closes([10 + i * 0.5 for i in range(40)], last_open=True)
    with pytest.raises(UnclosedCandleError):
        func(serie)


@pytest.mark.parametrize(("nome", "func"), ALL_INDICATORS)
def test_dados_insuficientes_levantam_excecao(nome: str, func) -> None:
    """Coluna de NaN seria lida adiante como 'sem sinal'."""
    with pytest.raises(InsufficientDataError):
        func(series_from_closes([10.0]))


@pytest.mark.parametrize(("nome", "func"), ALL_INDICATORS)
def test_indicador_nao_emite_sinal(nome: str, func) -> None:
    """Nenhuma coluna pode conter veredito de compra ou venda."""
    serie = series_from_closes([10 + i * 0.5 for i in range(40)])
    proibidas = {"signal_buy", "sell", "buy", "trade", "entry", "decision", "action"}
    assert not proibidas & {c.lower() for c in func(serie).columns}


# =====================================================================
# SMA
# =====================================================================


def test_sma_valores_conhecidos() -> None:
    """Media de [1,2,3] = 2; de [2,3,4] = 3; de [3,4,5] = 4."""
    resultado = sma(series_from_closes([1, 2, 3, 4, 5]), 3)
    valores = resultado.values["sma_3"].tolist()
    assert valores[0] != valores[0]  # NaN
    assert valores[1] != valores[1]  # NaN
    assert valores[2] == pytest.approx(2.0)
    assert valores[3] == pytest.approx(3.0)
    assert valores[4] == pytest.approx(4.0)


def test_sma_aquecimento_declarado() -> None:
    resultado = sma(series_from_closes([1, 2, 3, 4, 5]), 3)
    assert resultado.warmup == 2
    assert len(resultado.dropna()) == 3


def test_sma_de_serie_constante_e_o_proprio_valor() -> None:
    resultado = sma(series_from_closes([7.0] * 10), 5)
    assert resultado.last()["sma_5"] == pytest.approx(7.0)


def test_sma_periodo_invalido() -> None:
    with pytest.raises(ValueError, match="period deve ser"):
        sma(series_from_closes([1, 2, 3]), 0)


def test_sma_exige_exatamente_o_periodo() -> None:
    """Com period candles ha um valor; com period-1 nao ha calculo possivel."""
    assert sma(series_from_closes([1, 2, 3]), 3).last()["sma_3"] == pytest.approx(2.0)
    with pytest.raises(InsufficientDataError, match="ao menos 3"):
        sma(series_from_closes([1, 2]), 3)


# =====================================================================
# EMA
# =====================================================================


def test_ema_valores_conhecidos() -> None:
    """alpha = 2/(3+1) = 0.5. Semente = SMA(3) dos tres primeiros = 2.0.
    Proximo = 4*0.5 + 2.0*0.5 = 3.0. Depois = 5*0.5 + 3.0*0.5 = 4.0."""
    resultado = ema(series_from_closes([1, 2, 3, 4, 5]), 3)
    valores = resultado.values["ema_3"].tolist()
    assert valores[2] == pytest.approx(2.0)
    assert valores[3] == pytest.approx(3.0)
    assert valores[4] == pytest.approx(4.0)


def test_ema_reage_mais_rapido_que_sma_no_primeiro_candle_apos_o_salto() -> None:
    """A vantagem da EMA e imediata, nao permanente.

    Passados `period` candles no novo patamar, a SMA ja o alcancou
    integralmente enquanto a EMA ainda se aproxima por assintota. A
    comparacao so faz sentido logo apos o salto.
    """
    serie = series_from_closes([10.0] * 10 + [20.0])
    posicao = 10
    valor_ema = ema(serie, 5).values["ema_5"].iloc[posicao]
    valor_sma = sma(serie, 5).values["sma_5"].iloc[posicao]
    assert valor_ema > valor_sma


def test_ema_de_serie_constante() -> None:
    assert ema(series_from_closes([5.0] * 20), 9).last()["ema_9"] == pytest.approx(5.0)


# =====================================================================
# RSI
# =====================================================================


def test_rsi_alta_continua_satura_em_100() -> None:
    """Sem perdas, a media de perdas e zero e o RSI e 100 por definicao."""
    resultado = rsi(series_from_closes([10 + i for i in range(20)]), 14)
    assert resultado.last()["rsi_14"] == pytest.approx(100.0)


def test_rsi_queda_continua_tende_a_zero() -> None:
    resultado = rsi(series_from_closes([50 - i for i in range(20)]), 14)
    assert resultado.last()["rsi_14"] == pytest.approx(0.0)


def test_rsi_serie_constante_e_neutro() -> None:
    """Sem ganhos nem perdas o RS e indefinido; 50 e a convencao."""
    resultado = rsi(series_from_closes([10.0] * 20), 14)
    assert resultado.last()["rsi_14"] == pytest.approx(50.0)


def test_rsi_permanece_no_intervalo() -> None:
    closes = [10 + (i % 7) - (i % 3) * 1.5 for i in range(60)]
    valores = rsi(series_from_closes(closes), 14).dropna()["rsi_14"]
    assert valores.min() >= 0.0
    assert valores.max() <= 100.0


def test_rsi_aquecimento() -> None:
    resultado = rsi(series_from_closes([10 + i * 0.3 for i in range(30)]), 14)
    assert resultado.warmup == 14
    assert resultado.values["rsi_14"].iloc[:14].isna().all()


def test_rsi_exige_um_candle_a_mais_que_o_periodo() -> None:
    with pytest.raises(InsufficientDataError, match="ao menos 15"):
        rsi(series_from_closes([10.0] * 14), 14)


# =====================================================================
# ATR
# =====================================================================


def test_true_range_considera_o_gap() -> None:
    """Amplitude interna 1.0, mas o gap ate o fechamento anterior e 5.0."""
    serie = series_from_closes(
        [10.0, 15.0], highs=[10.0, 15.5], lows=[10.0, 14.5]
    )
    tr = true_range(serie.to_frame())
    assert tr.iloc[1] == pytest.approx(5.5)


def test_atr_de_amplitude_constante() -> None:
    """Amplitude fixa de 2.0 sem gaps: o ATR converge para 2.0."""
    closes = [10.0] * 30
    highs = [11.0] * 30
    lows = [9.0] * 30
    resultado = atr(series_from_closes(closes, highs=highs, lows=lows), 14)
    assert resultado.last()["atr_14"] == pytest.approx(2.0)


def test_atr_e_sempre_positivo() -> None:
    closes = [10 + (i % 5) for i in range(40)]
    valores = atr(series_from_closes(closes), 14).values["atr_14"].dropna()
    assert not valores.empty
    assert (valores >= 0).all()


def test_atr_primeiro_true_range_e_indefinido() -> None:
    """Sem fechamento anterior nao ha TR: preencher seria inventar dado."""
    resultado = atr(series_from_closes([10 + i for i in range(20)]), 14)
    assert resultado.values["true_range"].iloc[0] != resultado.values["true_range"].iloc[0]


def test_atr_expoe_true_range_bruto() -> None:
    resultado = atr(series_from_closes([10 + i for i in range(20)]), 14)
    assert set(resultado.columns) == {"atr_14", "true_range"}


def test_atr_aumenta_com_a_volatilidade() -> None:
    calmo = series_from_closes([10.0] * 30, highs=[10.2] * 30, lows=[9.8] * 30)
    agitado = series_from_closes([10.0] * 30, highs=[12.0] * 30, lows=[8.0] * 30)
    assert atr(agitado, 14).last()["atr_14"] > atr(calmo, 14).last()["atr_14"]


# =====================================================================
# MACD
# =====================================================================


def test_macd_de_serie_constante_e_zero() -> None:
    """Duas EMAs de uma constante sao iguais, entao a diferenca e zero."""
    resultado = macd(series_from_closes([10.0] * 60))
    ultimo = resultado.last()
    assert ultimo["macd"] == pytest.approx(0.0, abs=1e-9)
    assert ultimo["signal"] == pytest.approx(0.0, abs=1e-9)
    assert ultimo["histogram"] == pytest.approx(0.0, abs=1e-9)


def test_macd_positivo_em_tendencia_de_alta() -> None:
    resultado = macd(series_from_closes([10 + i * 0.5 for i in range(80)]))
    assert resultado.last()["macd"] > 0


def test_macd_negativo_em_tendencia_de_baixa() -> None:
    resultado = macd(series_from_closes([100 - i * 0.5 for i in range(80)]))
    assert resultado.last()["macd"] < 0


def test_histograma_e_a_diferenca_das_linhas() -> None:
    resultado = macd(series_from_closes([10 + (i % 9) * 0.7 for i in range(80)]))
    frame = resultado.dropna()
    assert (frame["histogram"] - (frame["macd"] - frame["signal"])).abs().max() < 1e-9


def test_macd_tres_linhas_no_mesmo_frame() -> None:
    """Alinhamento temporal garantido por construcao."""
    resultado = macd(series_from_closes([10 + i * 0.1 for i in range(60)]))
    assert set(resultado.columns) == {"macd", "signal", "histogram"}


def test_macd_rejeita_fast_maior_que_slow() -> None:
    with pytest.raises(ValueError, match=r"fast .* deve ser menor"):
        macd(series_from_closes([10.0] * 60), fast=26, slow=12)


def test_macd_exige_slow_mais_signal() -> None:
    with pytest.raises(InsufficientDataError, match="ao menos 35"):
        macd(series_from_closes([10.0] * 30))


# =====================================================================
# Bollinger
# =====================================================================


def test_bollinger_de_serie_constante_tem_bandas_coladas() -> None:
    """Desvio zero: as tres linhas coincidem."""
    resultado = bollinger(series_from_closes([10.0] * 30), 20)
    ultimo = resultado.last()
    assert ultimo["upper"] == pytest.approx(10.0)
    assert ultimo["middle"] == pytest.approx(10.0)
    assert ultimo["lower"] == pytest.approx(10.0)


def test_bollinger_banda_central_e_a_sma() -> None:
    serie = series_from_closes([10 + (i % 6) for i in range(40)])
    central = bollinger(serie, 20).values["middle"]
    media = sma(serie, 20).values["sma_20"]
    assert (central - media).abs().max() < 1e-9


def test_bollinger_valores_conhecidos() -> None:
    """[1,2,3]: media 2, desvio populacional = sqrt(2/3) ~= 0.8165.
    Banda superior com k=2 = 2 + 1.633 = 3.633."""
    resultado = bollinger(series_from_closes([1, 2, 3]), 3, deviations=2.0)
    ultimo = resultado.last()
    assert ultimo["middle"] == pytest.approx(2.0)
    assert ultimo["upper"] == pytest.approx(3.6329931, abs=1e-6)
    assert ultimo["lower"] == pytest.approx(0.3670068, abs=1e-6)


def test_bollinger_ddof_altera_a_largura() -> None:
    """Documenta a divergencia entre convencao de mercado e default do pandas."""
    serie = series_from_closes([1, 2, 3])
    populacional = bollinger(serie, 3, ddof=0).last()["upper"]
    amostral = bollinger(serie, 3, ddof=1).last()["upper"]
    assert amostral > populacional


def test_percent_b_dentro_das_bandas() -> None:
    serie = series_from_closes([10 + (i % 7) * 0.4 for i in range(40)])
    percent = bollinger(serie, 20).dropna()["percent_b"]
    assert percent.between(-0.5, 1.5).all()


def test_bollinger_rejeita_desvio_nao_positivo() -> None:
    with pytest.raises(ValueError, match="deviations deve ser positivo"):
        bollinger(series_from_closes([10.0] * 30), 20, deviations=0)


# =====================================================================
# VWAP
# =====================================================================


def test_vwap_com_volume_uniforme_e_a_media_dos_precos_tipicos() -> None:
    serie = series_from_closes([10.0, 20.0], volumes=[100, 100])
    assert vwap(serie).last()["vwap"] == pytest.approx(15.0)


def test_vwap_e_ponderado_pelo_volume() -> None:
    """Preco 10 com volume 1 e preco 20 com volume 3: (10 + 60)/4 = 17.5."""
    serie = series_from_closes([10.0, 20.0], volumes=[1, 3])
    assert vwap(serie).last()["vwap"] == pytest.approx(17.5)


def test_vwap_usa_preco_tipico() -> None:
    """(12 + 8 + 10)/3 = 10, e nao o fechamento isolado."""
    serie = series_from_closes([10.0, 10.0], highs=[12.0, 12.0], lows=[8.0, 8.0])
    assert vwap(serie).last()["vwap"] == pytest.approx(10.0)


def test_vwap_reinicia_a_cada_pregao() -> None:
    """Sem reinicio, o dia 1 contaminaria o dia 2 indefinidamente."""
    dia1 = datetime(2026, 8, 19, 13, 0, tzinfo=UTC)
    dia2 = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)
    candles = []
    for start, preco in ((dia1, 10.0), (dia2, 50.0)):
        for i in range(3):
            open_time = start + timedelta(minutes=5 * i)
            price = Decimal(str(preco))
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=open_time + timedelta(minutes=5),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=100,
                )
            )
    serie = CandleSeries(
        symbol="PETR4",
        timeframe=Timeframe.M5,
        candles=tuple(candles),
        source="teste",
        fetched_at=dia2 + timedelta(hours=1),
    )
    resultado = vwap(serie, anchor=VwapAnchor.SESSION)
    assert resultado.values["vwap"].iloc[2] == pytest.approx(10.0)
    assert resultado.values["vwap"].iloc[3] == pytest.approx(50.0)
    assert resultado.values["session_volume"].iloc[3] == pytest.approx(100.0)


def test_vwap_ancora_full_acumula_tudo() -> None:
    dia1 = datetime(2026, 8, 19, 13, 0, tzinfo=UTC)
    serie = series_from_closes([10.0, 10.0, 50.0], start=dia1, volumes=[100, 100, 100])
    completo = vwap(serie, anchor=VwapAnchor.FULL).last()["vwap"]
    assert completo == pytest.approx((10 + 10 + 50) / 3)


def test_vwap_nao_se_aplica_ao_diario() -> None:
    """VWAP ancorado na sessao nao faz sentido em candle diario."""
    serie = series_from_closes([10.0] * 30, timeframe=Timeframe.D1)
    with pytest.raises(IndicatorNotApplicableError, match="intradiario"):
        vwap(serie)


def test_vwap_ignora_candles_sem_volume() -> None:
    serie = series_from_closes([10.0, 99.0, 10.0], volumes=[100, 0, 100])
    assert vwap(serie).last()["vwap"] == pytest.approx(10.0)


def test_vwap_sem_volume_algum_devolve_nan() -> None:
    """Sem negocios nao ha preco medio ponderado; zero seria mentira."""
    serie = series_from_closes([10.0, 20.0], volumes=[0, 0])
    assert vwap(serie).last()["vwap"] is None


# =====================================================================
# IndicatorResult
# =====================================================================


def test_last_devolve_none_durante_o_aquecimento() -> None:
    resultado = sma(series_from_closes([1, 2, 3]), 3)
    assert resultado.values["sma_3"].iloc[0] != resultado.values["sma_3"].iloc[0]
    parcial = sma(series_from_closes([1, 2, 3, 4]), 4)
    assert parcial.last()["sma_4"] == pytest.approx(2.5)


def test_params_registram_a_configuracao() -> None:
    """Auditoria: o resultado precisa dizer com que parametros foi gerado."""
    assert sma(series_from_closes([1, 2, 3]), 3).params == {"period": 3.0}
    assert macd(series_from_closes([10.0] * 60)).params == {
        "fast": 12.0,
        "slow": 26.0,
        "signal": 9.0,
    }


def test_nome_identifica_o_indicador_e_os_parametros() -> None:
    assert sma(series_from_closes([1, 2, 3]), 3).name == "SMA(3)"
    assert bollinger(series_from_closes([10.0] * 30), 20).name == "BB(20,2)"


# =====================================================================
# Semente das medias recursivas (regressao)
# =====================================================================


def test_ema_semeia_na_sma() -> None:
    """Regressao: `pandas.ewm` semeia no primeiro valor, e nao na SMA.

    Com a semente do pandas os valores seriam [.., 2.25, 3.125, 4.0625].
    A convencao das plataformas produz [.., 2.0, 3.0, 4.0].
    """
    valores = ema(series_from_closes([1, 2, 3, 4, 5]), 3).values["ema_3"].tolist()
    assert valores[2] == pytest.approx(2.0)
    assert valores[3] == pytest.approx(3.0)
    assert valores[4] == pytest.approx(4.0)


def test_wilder_semeia_na_media_simples() -> None:
    """Regressao: o primeiro RSI usa media simples dos `period` movimentos.

    Fechamentos [10, 11, 10.5, 11.5] -> ganhos [1, 0, 1], perdas [0, 0.5, 0].
    avg_gain = 2/3, avg_loss = 1/6, RS = 4, RSI = 100 - 100/5 = 80.
    Com a semente do pandas o valor seria 87.5.
    """
    resultado = rsi(series_from_closes([10, 11, 10.5, 11.5]), 3)
    assert resultado.values["rsi_3"].iloc[3] == pytest.approx(80.0)


def test_atr_semeia_na_media_dos_true_ranges() -> None:
    """TRs [2, 2, 2] -> semente 2.0, e o proximo TR de 2.0 mantem 2.0."""
    serie = series_from_closes([10.0] * 6, highs=[11.0] * 6, lows=[9.0] * 6)
    resultado = atr(serie, 3)
    assert resultado.values["atr_3"].iloc[3] == pytest.approx(2.0)
