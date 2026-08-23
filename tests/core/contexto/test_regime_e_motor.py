"""Do conjunto de leituras ao regime - e o motor que monta o contexto."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.contexto import (
    DOLAR,
    IBOVESPA,
    MINERIO,
    NASDAQ,
    SP500,
    ConfigContexto,
    DirecaoDeMercado,
    EstadoDaLeitura,
    MotorDeContexto,
    NivelDeQualidade,
    NivelDeVolatilidade,
    RegimeDeMercado,
    classificar_regime,
)
from cashinho.models import BRT

from .factories import (
    ABERTURA,
    FonteFalsa,
    config,
    leitura,
    serie,
    serie_de_dias,
    serie_ruidosa,
)

NORMAL = NivelDeVolatilidade.NORMAL


# --- as regras do regime ------------------------------------------------------


def test_bolsa_em_alta_com_dolar_em_queda_e_risco_ligado():
    regime, motivos = classificar_regime(
        leitura(IBOVESPA, +1.2), leitura(DOLAR, -0.8), NORMAL)

    assert regime is RegimeDeMercado.RISCO_LIGADO
    assert any("Ibovespa" in m for m in motivos)


def test_bolsa_em_queda_com_dolar_em_alta_e_risco_desligado():
    regime, _ = classificar_regime(leitura(IBOVESPA, -1.5), leitura(DOLAR, +1.0), NORMAL)

    assert regime is RegimeDeMercado.RISCO_DESLIGADO


def test_indice_de_lado_e_lateral():
    regime, _ = classificar_regime(leitura(IBOVESPA, 0.05), leitura(DOLAR, +0.5), NORMAL)

    assert regime is RegimeDeMercado.LATERAL


def test_bolsa_e_dolar_no_mesmo_sentido_sao_sinais_conflitantes():
    """No Brasil os dois costumam andar em sentidos opostos."""
    regime, motivos = classificar_regime(
        leitura(IBOVESPA, +1.0), leitura(DOLAR, +1.0), NORMAL)

    assert regime is RegimeDeMercado.CONFLITANTE
    assert regime.rotulo != RegimeDeMercado.LATERAL.rotulo


def test_volatilidade_extrema_domina_a_direcao():
    regime, _ = classificar_regime(
        leitura(IBOVESPA, +2.0), leitura(DOLAR, -1.0), NivelDeVolatilidade.EXTREMA)

    assert regime is RegimeDeMercado.ESTRESSE


def test_queda_com_volatilidade_alta_e_estresse():
    regime, _ = classificar_regime(
        leitura(IBOVESPA, -2.0), leitura(DOLAR, +1.0), NivelDeVolatilidade.ALTA)

    assert regime is RegimeDeMercado.ESTRESSE


def test_sem_ibovespa_nao_ha_regime():
    regime, motivos = classificar_regime(None, leitura(DOLAR, +1.0), NORMAL)

    assert regime is RegimeDeMercado.INDEFINIDO
    assert regime.conhecido is False
    assert "Ibovespa" in motivos[0]


def test_ibovespa_indisponivel_nao_vira_lateral():
    """Faltar dado nao e' 'mercado de lado'."""
    ruim = leitura(IBOVESPA, None, estado=EstadoDaLeitura.INDISPONIVEL, ultimo=None)
    regime, _ = classificar_regime(ruim, leitura(DOLAR, +1.0), NORMAL)

    assert regime is RegimeDeMercado.INDEFINIDO


def test_sem_dolar_o_regime_sai_so_com_o_indice():
    regime, motivos = classificar_regime(leitura(IBOVESPA, +1.0), None, NORMAL)

    assert regime is RegimeDeMercado.RISCO_LIGADO
    assert any("sem leitura de dolar" in m for m in motivos)


def test_indices_internacionais_entram_como_leitura():
    _, motivos = classificar_regime(
        leitura(IBOVESPA, +1.0), leitura(DOLAR, -0.5), NORMAL,
        [leitura(SP500, +0.8), leitura(NASDAQ, +1.1)])

    assert any("internacional" in m for m in motivos)


# --- o motor -----------------------------------------------------------------------


def test_monta_o_contexto_com_os_seis_campos_pedidos():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=4, passo=0.004),
                        "dolar": serie_de_dias(dias=4, passo=-0.002)})
    ctx = MotorDeContexto(fonte, config()).montar()

    assert ctx.timestamp is not None
    assert ctx.market_regime in RegimeDeMercado
    assert ctx.ibovespa_direction in DirecaoDeMercado
    assert ctx.volatility in NivelDeVolatilidade
    assert isinstance(ctx.relevant_correlations, tuple)
    assert ctx.data_quality is not None


def test_instrumento_sem_fonte_aparece_sem_numero():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3)})
    ctx = MotorDeContexto(fonte, config()).montar()

    minerio = ctx.leitura("minerio")
    assert minerio.estado is EstadoDaLeitura.SEM_FONTE
    assert minerio.ultimo is None and minerio.variacao_pct is None
    assert "FONTE A CONFIRMAR" in minerio.detalhe


def test_o_motor_nem_tenta_buscar_o_que_nao_tem_fonte():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3)})
    MotorDeContexto(fonte, config()).montar()

    assert "minerio" not in fonte.pedidos


def test_falha_da_fonte_vira_indisponivel_com_o_motivo():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3)},
                       erros={"dolar": "a fonte caiu"})
    ctx = MotorDeContexto(fonte, config()).montar()

    dolar = ctx.leitura("dolar")
    assert dolar.estado is EstadoDaLeitura.INDISPONIVEL
    assert dolar.ultimo is None
    assert "caiu" in dolar.detalhe


def test_fonte_que_responde_vazio_nao_vira_leitura():
    from cashinho.models import Series

    fonte = FonteFalsa({"ibovespa": Series("X", "60m", [])})
    ctx = MotorDeContexto(fonte, config(instrumentos=("ibovespa",))).montar()

    assert ctx.leitura("ibovespa").estado is EstadoDaLeitura.INDISPONIVEL


def test_dado_velho_vira_atrasado():
    s = serie_de_dias(dias=3)
    instante = s.candles[-1].ts + timedelta(hours=6)
    fonte = FonteFalsa({"ibovespa": s})

    ctx = MotorDeContexto(fonte, config(defasagem_aceitavel_min=30)).montar(instante)
    ibov = ctx.leitura("ibovespa")

    assert ibov.estado is EstadoDaLeitura.ATRASADA
    assert ibov.defasagem_minutos >= 360


def test_serie_diaria_tolera_mais_atraso_que_intradiario():
    """Juros muda uma vez por dia: um dia de idade nao e' falha."""
    s = serie([10.5, 10.65], timeframe="1d", passo_min=60 * 24)
    instante = s.candles[-1].ts + timedelta(hours=20)
    fonte = FonteFalsa({"juros": s})

    ctx = MotorDeContexto(fonte, config(instrumentos=("juros",))).montar(instante)

    assert ctx.leitura("juros").estado is EstadoDaLeitura.OK


def test_a_direcao_do_ibovespa_sai_da_variacao_do_dia():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3, passo=0.01)})
    ctx = MotorDeContexto(fonte, config(instrumentos=("ibovespa",))).montar()

    assert ctx.ibovespa_direction is DirecaoDeMercado.ALTA


def test_sem_ibovespa_a_direcao_e_indisponivel_e_nao_lateral():
    fonte = FonteFalsa(erros={"ibovespa": "caiu"})
    ctx = MotorDeContexto(fonte, config(instrumentos=("ibovespa",))).montar()

    assert ctx.ibovespa_direction is DirecaoDeMercado.INDISPONIVEL
    assert ctx.market_regime is RegimeDeMercado.INDEFINIDO


# --- qualidade dos dados --------------------------------------------------------------


def test_qualidade_boa_com_tudo_no_ar():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3), "dolar": serie_de_dias(dias=3)})
    ctx = MotorDeContexto(fonte, config()).montar(ABERTURA + timedelta(days=2, hours=17))

    assert ctx.data_quality.nivel is NivelDeQualidade.BOA
    assert ctx.data_quality.disponiveis == 2
    assert ctx.data_quality.esperados == 2  # minerio nao conta: nao tem fonte


def test_o_que_nao_tem_fonte_aparece_a_parte_e_nao_como_falha():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3), "dolar": serie_de_dias(dias=3)})
    q = MotorDeContexto(fonte, config()).montar().data_quality

    assert "Minerio de ferro" in q.sem_fonte
    assert "Minerio de ferro" not in q.faltantes
    assert any("nao sao estimados" in n for n in q.notas)


def test_metade_das_fontes_no_ar_e_qualidade_parcial():
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3)},
                       erros={"dolar": "caiu", "sp500": "caiu"})
    ctx = MotorDeContexto(fonte, config(instrumentos=("ibovespa", "dolar", "sp500"))).montar()

    assert ctx.data_quality.nivel in (NivelDeQualidade.PARCIAL, NivelDeQualidade.RUIM)
    assert "Dolar (USD/BRL)" in ctx.data_quality.faltantes


def test_nenhuma_fonte_respondendo_e_qualidade_indisponivel():
    fonte = FonteFalsa(erros={"ibovespa": "caiu", "dolar": "caiu"})
    ctx = MotorDeContexto(fonte, config()).montar()

    q = ctx.data_quality
    assert q.nivel is NivelDeQualidade.INDISPONIVEL
    assert q.confiavel is False
    assert ctx.utilizavel is False


def test_dado_simulado_e_medido_mas_nunca_confiavel():
    """A tela mostra tudo; a decisao continua barrada."""
    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=4, passo=0.01),
                        "dolar": serie_de_dias(dias=4, passo=-0.01)}, simulada=True)
    ctx = MotorDeContexto(fonte, config()).montar()

    assert ctx.leitura("ibovespa").ultimo is not None      # medido
    assert ctx.ibovespa_direction.conhecida                 # medido
    assert ctx.data_quality.nivel is NivelDeQualidade.SIMULADA
    assert ctx.data_quality.confiavel is False              # nao confiavel
    assert ctx.utilizavel is False
    assert any("NAO pode pesar" in n for n in ctx.notas)


def test_as_correlacoes_do_ativo_entram_quando_informadas():
    ibov = serie_ruidosa(n=120, semente=3, symbol="IBOV")
    fonte = FonteFalsa({"ibovespa": ibov})
    from cashinho.models import Series

    espelho = Series("PETR4", ibov.timeframe, list(ibov.candles))

    ctx = MotorDeContexto(fonte, config(instrumentos=("ibovespa",), limiar_correlacao=0.5)
                          ).montar(series_do_ativo={"PETR4": espelho})

    pares = {(c.a, c.b) for c in ctx.relevant_correlations}
    assert ("Ibovespa", "PETR4") in pares or ("PETR4", "Ibovespa") in pares


def test_o_contexto_serializa_para_json():
    import json

    fonte = FonteFalsa({"ibovespa": serie_de_dias(dias=3)})
    ctx = MotorDeContexto(fonte, config()).montar()

    dados = json.loads(json.dumps(ctx.para_dict()))
    assert set(dados) >= {"timestamp", "market_regime", "ibovespa_direction",
                          "volatility", "relevant_correlations", "data_quality"}
