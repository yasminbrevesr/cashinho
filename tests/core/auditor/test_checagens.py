"""As onze frentes de invalidacao, uma a uma."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.auditor.checagens import (
    CHECAGENS,
    ConfigAuditor,
    baixo_volume,
    divergencias,
    entrada_atrasada,
    falso_rompimento,
    oportunidade_expirada,
    resistencia_proxima,
    risco_retorno_ruim,
    stop_muito_distante,
    suporte_proximo,
    timeframes_conflitantes,
    volatilidade_excessiva,
)
from cashinho.core.auditor.modelos import Severidade
from cashinho.core.confluencia.estados import ContextState, TrendState, Vies
from cashinho.core.structure.models import Regime, TipoEvento, TipoPivo
from cashinho.models import Direction

from .factories import (
    AGORA,
    contexto,
    estrutura,
    evento,
    nivel,
    oportunidade,
    pivo,
    serie,
)


def test_as_onze_frentes_pedidas_existem():
    nomes = {c.__name__ for c in CHECAGENS}

    assert nomes == {
        "resistencia_proxima", "suporte_proximo", "baixo_volume", "divergencias",
        "entrada_atrasada", "risco_retorno_ruim", "volatilidade_excessiva",
        "falso_rompimento", "timeframes_conflitantes", "stop_muito_distante",
        "oportunidade_expirada",
    }


# --- 1 e 2: zonas ---------------------------------------------------------------


def test_resistencia_colada_na_compra_e_critica():
    ctx = contexto(est=estrutura(resistencias=[nivel(31.05, 31.10, "resistencia")]))
    c = resistencia_proxima(ctx)

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "0.2 ATR" in c.detalhe or "ATR da entrada" in c.detalhe


def test_resistencia_a_meia_distancia_e_alerta():
    ctx = contexto(est=estrutura(resistencias=[nivel(31.25, 31.28, "resistencia")]))
    c = resistencia_proxima(ctx)

    assert c.passou is False
    assert c.severidade is Severidade.ALERTA


def test_resistencia_longe_vira_fator_favoravel():
    ctx = contexto(est=estrutura(resistencias=[nivel(32.00, 32.05, "resistencia")]))
    c = resistencia_proxima(ctx)

    assert c.passou is True
    assert "espaco livre" in c.detalhe


def test_resistencia_na_venda_conta_a_favor():
    op = oportunidade(direction=Direction.SHORT, entry=31.0, stop=31.3, target=30.4)
    ctx = contexto(op=op, est=estrutura(resistencias=[nivel(31.05, 31.10, "resistencia")]))
    c = resistencia_proxima(ctx)

    assert c.passou is True
    assert "a favor da venda" in c.detalhe


def test_suporte_colado_na_venda_e_critico():
    op = oportunidade(direction=Direction.SHORT, entry=31.0, stop=31.3, target=30.4)
    ctx = contexto(op=op, est=estrutura(suportes=[nivel(30.92, 30.96, "suporte")]))
    c = suporte_proximo(ctx)

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO


def test_suporte_na_compra_e_apoio():
    ctx = contexto(est=estrutura(suportes=[nivel(30.90, 30.95, "suporte")]))
    c = suporte_proximo(ctx)

    assert c.passou is True
    assert "apoio" in c.detalhe


# --- 3: volume -------------------------------------------------------------------


def test_volume_muito_baixo_e_critico():
    fraca = serie([31.0] * 40, timeframe="1m", volumes=[10_000.0] * 39 + [3_000.0])
    c = baixo_volume(contexto(serie_trigger=fraca))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "participacao" in c.detalhe


def test_volume_abaixo_da_media_e_alerta():
    fraca = serie([31.0] * 40, timeframe="1m", volumes=[10_000.0] * 39 + [8_500.0])
    c = baixo_volume(contexto(serie_trigger=fraca))

    assert c.passou is False
    assert c.severidade is Severidade.ALERTA


def test_volume_forte_vira_favoravel():
    forte = serie([31.0] * 40, timeframe="1m", volumes=[10_000.0] * 39 + [25_000.0])
    c = baixo_volume(contexto(serie_trigger=forte))

    assert c.passou is True


# --- 4: divergencias ---------------------------------------------------------------


def test_divergencia_de_alta_e_detectada():
    """Preco fez topo mais alto, RSI nao acompanhou."""
    closes = [30.0 + i * 0.05 for i in range(30)] + [31.5 - i * 0.04 for i in range(10)]
    closes += [31.2 + i * 0.02 for i in range(20)]
    s = serie(closes)
    est = estrutura(
        preco=s.price,
        swing_highs=[pivo(28, 31.40), pivo(58, 31.60)],  # topo mais alto
    )
    c = divergencias(contexto(est=est, serie_setup=s))

    assert c.verificada
    if not c.passou:
        assert c.severidade is Severidade.ALERTA
        assert "momentum nao acompanha" in c.detalhe


def test_sem_dois_swings_a_divergencia_nao_e_verificada():
    c = divergencias(contexto(est=estrutura(swing_highs=[pivo(10, 31.0)])))

    assert c.verificada is False
    assert c.passou is False  # nao vira favoravel


# --- 5: entrada atrasada ------------------------------------------------------------


def test_entrada_muito_esticada_e_critica():
    s = serie([30.0] * 55 + [31.0])  # EMA21 bem abaixo da entrada
    ctx = contexto(op=oportunidade(entry=32.0, stop=31.7, target=32.6),
                   est=estrutura(preco=32.0, atr=0.15), serie_setup=s)
    c = entrada_atrasada(ctx)

    assert c.passou is False
    assert c.severidade in (Severidade.CRITICO, Severidade.ALERTA)


def test_entrada_perto_da_media_e_favoravel():
    s = serie([31.0] * 60)
    c = entrada_atrasada(contexto(serie_setup=s))

    assert c.passou is True
    assert "sem esticamento" in c.detalhe


# --- 6: risco/retorno ----------------------------------------------------------------


def test_rr_ruim_e_critico():
    c = risco_retorno_ruim(contexto(op=oportunidade(entry=31.0, stop=30.7, target=31.3)))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "nao paga o risco" in c.detalhe


def test_rr_mediano_e_alerta():
    c = risco_retorno_ruim(contexto(op=oportunidade(entry=31.0, stop=30.7, target=31.45)))

    assert c.passou is False
    assert c.severidade is Severidade.ALERTA


def test_rr_bom_e_favoravel():
    c = risco_retorno_ruim(contexto(op=oportunidade(entry=31.0, stop=30.7, target=31.9)))

    assert c.passou is True


# --- 7: volatilidade --------------------------------------------------------------------


def test_volatilidade_excessiva_e_critica():
    c = volatilidade_excessiva(contexto(est=estrutura(atr=1.2)))  # 3.9% de 31,00

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "ruido engole" in c.detalhe


def test_volatilidade_normal_e_favoravel():
    c = volatilidade_excessiva(contexto(est=estrutura(atr=0.15)))

    assert c.passou is True


# --- 8: falso rompimento -------------------------------------------------------------------


def test_comprar_no_sentido_do_rompimento_que_falhou_e_critico():
    """A reversao aponta para baixo; comprar aqui e' entrar na armadilha."""
    est = estrutura(eventos=[evento(TipoEvento.POSSIVEL_FALSO_ROMPIMENTO, Direction.SHORT)])
    c = falso_rompimento(contexto(est=est))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "sentido do rompimento que falhou" in c.detalhe


def test_operar_a_favor_da_reversao_e_favoravel():
    est = estrutura(eventos=[evento(TipoEvento.POSSIVEL_FALSO_ROMPIMENTO, Direction.LONG)])
    c = falso_rompimento(contexto(est=est))

    assert c.passou is True


def test_sem_falso_rompimento_e_favoravel():
    assert falso_rompimento(contexto()).passou is True


# --- 9: timeframes conflitantes ---------------------------------------------------------------


def test_uma_camada_contra_e_alerta():
    op = oportunidade(context=ContextState.BEARISH)
    c = timeframes_conflitantes(contexto(op=op))

    assert c.passou is False
    assert c.severidade is Severidade.ALERTA


def test_duas_camadas_contra_e_critico():
    op = oportunidade(context=ContextState.BEARISH, trend=TrendState.BEARISH)
    c = timeframes_conflitantes(contexto(op=op))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO


def test_duas_camadas_neutras_viram_alerta():
    op = oportunidade(context=ContextState.NEUTRAL, trend=TrendState.SIDEWAYS)
    c = timeframes_conflitantes(contexto(op=op))

    assert c.passou is False
    assert "pouca confluencia" in c.detalhe


def test_camadas_alinhadas_sao_favoraveis():
    assert timeframes_conflitantes(contexto()).passou is True


# --- 10: stop distante --------------------------------------------------------------------------


def test_stop_muito_distante_e_critico():
    op = oportunidade(entry=31.0, stop=29.5, target=34.0)  # 7,5 ATR
    c = stop_muito_distante(contexto(op=op))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "longe demais" in c.detalhe


def test_stop_um_pouco_largo_e_alerta():
    op = oportunidade(entry=31.0, stop=30.44, target=32.2)  # 2,8 ATR
    c = stop_muito_distante(contexto(op=op))

    assert c.passou is False
    assert c.severidade is Severidade.ALERTA


def test_stop_ajustado_e_favoravel():
    assert stop_muito_distante(contexto()).passou is True


# --- 11: expiracao ---------------------------------------------------------------------------------


def test_oportunidade_expirada_e_critica():
    op = oportunidade(expires_at=AGORA - timedelta(minutes=5))
    c = oportunidade_expirada(contexto(op=op, agora=AGORA))

    assert c.passou is False
    assert c.severidade is Severidade.CRITICO
    assert "janela terminou" in c.detalhe


def test_oportunidade_no_prazo_e_favoravel():
    c = oportunidade_expirada(contexto(op=oportunidade(expires_at=AGORA + timedelta(minutes=2))))

    assert c.passou is True
    assert "restantes" in c.detalhe


# --- sem dados ----------------------------------------------------------------------------------------


def test_sem_mercado_as_checagens_nao_sao_verificadas():
    from cashinho.core.auditor.checagens import ContextoAuditoria

    ctx = ContextoAuditoria(op=oportunidade(), agora=AGORA)  # sem estrutura nem series
    for checagem in (resistencia_proxima, suporte_proximo, baixo_volume, divergencias,
                     entrada_atrasada, falso_rompimento):
        c = checagem(ctx)
        assert c.verificada is False, f"{c.chave} deveria ficar sem verificacao"
        assert c.passou is False  # ausencia de evidencia nao e' evidencia de ausencia


def test_limiares_sao_configuraveis():
    frouxo = ConfigAuditor(rr_critico=0.1, rr_alerta=0.2)
    op = oportunidade(entry=31.0, stop=30.7, target=31.3)  # RR 1,0

    assert risco_retorno_ruim(contexto(op=op)).severidade is Severidade.CRITICO
    assert risco_retorno_ruim(contexto(op=op, cfg=frouxo)).passou is True
