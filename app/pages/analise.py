"""Analise do ativo — primeira fatia vertical do sistema.

Fluxo: entrada do usuario -> provider -> portao de qualidade -> grafico.
Nenhuma decisao de qualidade acontece nesta camada; a tela consome o
resultado de `load_market_data` e apenas o renderiza.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import streamlit as st

from app.components.charts import candlestick_figure
from app.components.chrome import page_header, sidebar
from app.components.quality import quality_panel
from cashinho.adapters.providers.csv_provider import (
    CsvHistoricalProvider,
    ProviderError,
)
from cashinho.config.settings import get_settings
from cashinho.core.time.clocks import SystemClock
from cashinho.domain.enums import Mode
from cashinho.pipeline.indicators import IndicatorSelection, compute_panel
from cashinho.pipeline.market_data import load_market_data

INSPECTION_MODE = Mode.RESEARCH
"""Esta tela e inspecao historica, nao decisao ao vivo.

Por D9, uma fonte sem tempo real nao habilita PAPER. Visualizar candles
passados, porem, nao e uma decisao operacional: e leitura de historico,
que e exatamente o que RESEARCH designa.

A escolha e explicita e visivel na tela, nao um rebaixamento silencioso
do modo. O modo operacional do sistema continua sendo o da barra lateral,
e as decisoes de oportunidade (Fase 5) usarao `settings.mode`, nunca esta
constante.
"""

settings = get_settings()
sidebar(settings)
page_header("Análise", "Carga de candles, verificação de qualidade e visualização")

FIXTURES = settings.data_dir / "fixtures"
clock = SystemClock()
provider = CsvHistoricalProvider(FIXTURES, clock, name="csv-fixtures")

symbols = provider.list_symbols()
if not symbols:
    st.error(
        "Nenhum dado disponível. Gere as séries de desenvolvimento com:\n\n"
        "```\npython scripts/generate_fixtures.py\n```",
        icon="⛔",
    )
    st.stop()

st.warning(
    "Fonte ativa: **arquivos CSV locais**. As séries de desenvolvimento são "
    "**sintéticas** e não correspondem a preços reais negociados na B3.",
    icon="⚠️",
)

if settings.mode.requires_realtime_data:
    st.info(
        f"Modo operacional: **{settings.mode.value}**. Esta tela executa "
        f"**inspeção histórica** (`{INSPECTION_MODE.value}`), porque a fonte atual "
        "não fornece dados em tempo real. Nenhum resultado aqui habilita decisão "
        "ao vivo.",
        icon="🔎",
    )

col1, col2, col3, col4 = st.columns([1.2, 1, 1, 1])

with col1:
    symbol = st.selectbox("Ativo", options=symbols, index=0)

available = provider.get_available_timeframes(symbol)
with col2:
    timeframe = st.selectbox(
        "Timeframe",
        options=available,
        index=min(1, len(available) - 1),
        format_func=lambda tf: tf.value,
    )

hoje = datetime.now(UTC).date()
with col3:
    start_date = st.date_input("Início", value=hoje - timedelta(days=30), format="DD/MM/YYYY")
with col4:
    end_date = st.date_input("Fim", value=hoje, format="DD/MM/YYYY")

if start_date > end_date:
    st.error("A data inicial não pode ser posterior à data final.", icon="⛔")
    st.stop()

with st.expander("Indicadores", expanded=True):
    st.caption(
        "Indicadores fornecem números. Nenhum deles gera sinal de compra ou venda: "
        "a confluência é avaliada pelas camadas de estratégia e score."
    )
    ind1, ind2, ind3 = st.columns(3)

    with ind1:
        st.markdown("**Sobre o preço**")
        usar_sma = st.checkbox("SMA", value=True)
        sma_periods = st.multiselect(
            "Períodos SMA", [9, 20, 50, 200], default=[20], disabled=not usar_sma
        )
        usar_ema = st.checkbox("EMA", value=True)
        ema_periods = st.multiselect(
            "Períodos EMA", [9, 12, 21, 26, 50], default=[9], disabled=not usar_ema
        )

    with ind2:
        st.markdown("**Referências**")
        usar_vwap = st.checkbox("VWAP", value=True, disabled=not timeframe.is_intraday)
        if not timeframe.is_intraday:
            st.caption("VWAP é intradiário: não se aplica ao diário.")
        usar_bb = st.checkbox("Bandas de Bollinger", value=False)
        bb_period = st.number_input(
            "Período BB", min_value=2, max_value=200, value=20, disabled=not usar_bb
        )
        bb_dev = st.number_input(
            "Desvios BB", min_value=0.5, max_value=5.0, value=2.0, step=0.5,
            disabled=not usar_bb,
        )

    with ind3:
        st.markdown("**Osciladores**")
        usar_rsi = st.checkbox("RSI", value=True)
        rsi_period = st.number_input(
            "Período RSI", min_value=2, max_value=100, value=14, disabled=not usar_rsi
        )
        usar_macd = st.checkbox("MACD (12, 26, 9)", value=True)
        usar_atr = st.checkbox("ATR", value=True)
        atr_period = st.number_input(
            "Período ATR", min_value=2, max_value=100, value=14, disabled=not usar_atr
        )

    mostrar_volume = st.checkbox("Volume", value=True)

selection = IndicatorSelection(
    sma_periods=tuple(sma_periods) if usar_sma else (),
    ema_periods=tuple(ema_periods) if usar_ema else (),
    vwap=usar_vwap and timeframe.is_intraday,
    bollinger_period=int(bb_period) if usar_bb else None,
    bollinger_deviations=float(bb_dev),
    rsi_period=int(rsi_period) if usar_rsi else None,
    macd=usar_macd,
    atr_period=int(atr_period) if usar_atr else None,
)

carregar = st.button("Carregar candles", type="primary")
if not carregar:
    st.info("Defina os parâmetros e carregue os candles.", icon="📈")
    st.stop()

start = datetime.combine(start_date, time.min, tzinfo=UTC)
end = datetime.combine(end_date, time.min, tzinfo=UTC) + timedelta(days=1)

try:
    result = load_market_data(
        provider,
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        clock=clock,
        mode=INSPECTION_MODE,
    )
except ProviderError as exc:
    st.error(f"Falha ao carregar dados: {exc}", icon="⛔")
    st.stop()

st.divider()
quality_panel(result.report, rejection_reason=result.rejection_reason)

series = result.usable_series
if series is None:
    st.stop()

panel = compute_panel(series, selection)

if panel.failures:
    for label, motivo in panel.failures.items():
        st.warning(f"**{label}** não calculado — {motivo}", icon="⚠️")

st.divider()
st.plotly_chart(
    candlestick_figure(
        series,
        display_timezone=settings.display_timezone,
        panel=panel,
        show_volume=mostrar_volume,
    ),
    use_container_width=True,
)

if panel.has_content:
    with st.expander("Últimos valores dos indicadores", expanded=False):
        linhas = []
        for label, resultado in {**panel.overlays, **panel.oscillators}.items():
            for coluna, valor in resultado.last().items():
                linhas.append(
                    {
                        "Indicador": label,
                        "Linha": coluna,
                        "Valor": "—" if valor is None else f"{valor:,.4f}",
                        "Aquecimento": resultado.warmup,
                    }
                )
        st.dataframe(linhas, use_container_width=True, hide_index=True)
        st.caption(
            "Períodos em aquecimento ficam vazios por construção: um valor "
            "calculado sobre janela incompleta pareceria válido sem ser."
        )

primeiro, ultimo = series.candles[0], series.candles[-1]
variacao = (ultimo.close - primeiro.open) / primeiro.open * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Candles", len(series))
col2.metric("Último fechamento", f"R$ {ultimo.close}")
col3.metric("Variação no período", f"{variacao:.2f}%")
col4.metric("Volume total", f"{sum(c.volume for c in series.candles):,}".replace(",", "."))

st.caption(
    f"Período efetivo: {primeiro.timestamp.astimezone().strftime('%d/%m/%Y %H:%M')} "
    f"até {ultimo.close_time.astimezone().strftime('%d/%m/%Y %H:%M')} · "
    f"origem `{series.source}` · coleta {series.fetched_at.strftime('%H:%M:%S UTC')}"
)

with st.expander("Dados carregados (forma tabular)"):
    st.dataframe(series.to_records()[-200:], use_container_width=True, hide_index=True)
