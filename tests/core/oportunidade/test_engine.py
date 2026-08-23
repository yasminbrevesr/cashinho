"""O Opportunity Engine: campos, estados, prazos e criterios de aprovacao."""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

import pytest

from cashinho.core.confluencia import MultiTimeframeEngine
from cashinho.core.oportunidade import (
    ConfigOportunidade,
    EstadoOportunidade,
    Opportunity,
    OpportunityEngine,
    PESOS_PADRAO,
)
from cashinho.data.synthetic import SyntheticProvider
from cashinho.models import Direction

SERIE = SyntheticProvider(semente=11).candles("PETR4", "1m", 3)


def _oportunidades(engine=None, limite=None):
    engine = engine or OpportunityEngine()
    mtf = engine.alimentar(SERIE)
    saida = []
    for vista in mtf.replay():
        saida.append(engine.avaliar(vista, "PETR4"))
        if limite and len(saida) >= limite:
            break
    return saida


TODAS = _oportunidades()
APROVADAS = [o for o in TODAS if o.estado is EstadoOportunidade.APROVADO]


# ---------------------------------------------------------------------------
# o contrato de campos
# ---------------------------------------------------------------------------


def test_a_oportunidade_tem_exatamente_os_campos_pedidos():
    pedidos = {
        "symbol", "timestamp", "direction", "setup", "score", "entry", "stop", "target",
        "risk_reward", "timeframe_context", "timeframe_trend", "timeframe_setup",
        "timeframe_trigger", "reasons", "warnings", "invalidation", "expires_at",
    }
    campos = {f.name for f in dataclasses.fields(Opportunity)}

    assert pedidos <= campos


def test_os_timeframes_de_cada_camada_sao_registrados():
    op = TODAS[-1]

    assert op.timeframe_context == "60m"
    assert op.timeframe_trend == "15m"
    assert op.timeframe_setup == "5m"
    assert op.timeframe_trigger == "1m"
    assert op.timeframes["context"] == "60m"


def test_o_score_fica_entre_0_e_100_sempre():
    for op in TODAS[::50]:
        assert 0.0 <= op.score <= 100.0


def test_risk_reward_bate_com_os_niveis():
    for op in APROVADAS[:5]:
        esperado = abs(op.target - op.entry) / abs(op.entry - op.stop)
        assert op.risk_reward == pytest.approx(esperado, abs=0.01)


def test_oportunidade_serializa_inteira():
    op = APROVADAS[0] if APROVADAS else TODAS[-1]
    dados = op.para_dict()
    texto = json.dumps(dados)

    assert dados["symbol"] == "PETR4"
    assert "score_detalhado" in dados
    assert '"estado"' in texto


def test_oportunidade_nao_tem_quantidade():
    campos = {f.name for f in dataclasses.fields(Opportunity)}
    assert not campos & {"quantidade", "position_size", "ordem", "boleta"}


# ---------------------------------------------------------------------------
# os cinco estados
# ---------------------------------------------------------------------------


def test_os_cinco_estados_existem_com_os_rotulos_pedidos():
    rotulos = {e.value for e in EstadoOportunidade}

    assert rotulos == {"SETUP APROVADO", "AGUARDANDO GATILHO", "SETUP REJEITADO",
                       "NAO OPERAR", "EXPIRADO"}


def test_uma_sessao_produz_os_estados_operacionais():
    estados = {o.estado for o in TODAS}

    assert EstadoOportunidade.NAO_OPERAR in estados
    assert EstadoOportunidade.REJEITADO in estados
    assert EstadoOportunidade.AGUARDANDO_GATILHO in estados


def test_camada_faltando_vira_nao_operar():
    engine = OpportunityEngine()
    mtf = engine.alimentar(SERIE)
    primeira = engine.avaliar(next(iter(mtf.replay())), "PETR4")

    assert primeira.estado is EstadoOportunidade.NAO_OPERAR
    assert "sem candle fechado" in primeira.motivo_do_estado
    assert primeira.direction is None
    assert primeira.entry == 0.0


def test_todo_estado_explica_o_motivo():
    for op in TODAS[::40]:
        assert op.motivo_do_estado, f"{op.estado} sem motivo"


def test_aguardando_gatilho_diz_o_que_falta():
    esperando = [o for o in TODAS if o.estado is EstadoOportunidade.AGUARDANDO_GATILHO]

    assert esperando
    assert "aguardando gatilho" in esperando[0].motivo_do_estado


def test_so_o_aprovado_e_acionavel():
    for op in TODAS[::30]:
        assert op.acionavel == (op.estado is EstadoOportunidade.APROVADO)


# ---------------------------------------------------------------------------
# expiracao
# ---------------------------------------------------------------------------


def test_oportunidade_ganha_prazo_de_validade():
    op = APROVADAS[0]

    assert op.expires_at is not None
    assert op.expires_at > op.timestamp
    assert op.validade_minutos() == pytest.approx(3.0)  # 3 candles de 1m


def test_prazo_de_validade_e_configuravel():
    engine = OpportunityEngine(config=ConfigOportunidade(expiracao_candles_gatilho=10))
    mtf = engine.alimentar(SERIE)
    for vista in mtf.replay():
        op = engine.avaliar(vista, "PETR4")
        if op.expires_at:
            assert op.validade_minutos() == pytest.approx(10.0)
            break


def test_passado_o_prazo_o_estado_vira_expirado():
    op = APROVADAS[0]
    depois = op.expires_at + timedelta(minutes=1)

    assert op.expirada_em(depois) is True
    assert op.estado_em(depois) is EstadoOportunidade.EXPIRADO
    assert op.estado is EstadoOportunidade.APROVADO  # o registro original nao muda


def test_dentro_do_prazo_o_estado_se_mantem():
    op = APROVADAS[0]
    assert op.estado_em(op.expires_at) is EstadoOportunidade.APROVADO


def test_estado_reprovado_nao_vira_expirado():
    rejeitada = next(o for o in TODAS if o.estado is EstadoOportunidade.REJEITADO)
    tarde = rejeitada.timestamp + timedelta(days=1)

    assert rejeitada.estado_em(tarde) is EstadoOportunidade.REJEITADO


# ---------------------------------------------------------------------------
# criterios de aprovacao
# ---------------------------------------------------------------------------


def test_score_minimo_e_respeitado():
    exigente = OpportunityEngine(config=ConfigOportunidade(score_minimo=99.0))
    aprovadas = [o for o in _oportunidades(exigente, limite=800) if o.acionavel]

    assert aprovadas == []


def test_score_baixo_e_rejeitado_com_os_piores_componentes_no_motivo():
    exigente = OpportunityEngine(config=ConfigOportunidade(score_minimo=99.0))
    # sem limite: a rejeicao por score exige que uma regra tenha fechado antes
    rejeitadas = [o for o in _oportunidades(exigente)
                  if o.estado is EstadoOportunidade.REJEITADO and "score" in o.motivo_do_estado]

    assert rejeitadas
    assert "pesa contra" in rejeitadas[0].motivo_do_estado


def test_componente_critico_abaixo_do_piso_reprova_por_mais_alto_que_esteja_o_score():
    """A media ponderada nao pode enterrar uma falha critica."""
    engine = OpportunityEngine(
        config=ConfigOportunidade(score_minimo=0.0, notas_minimas={"gatilho": 99.0})
    )
    resultados = _oportunidades(engine, limite=800)
    reprovadas = [o for o in resultados if "abaixo do piso" in o.motivo_do_estado]

    assert reprovadas
    assert all(not o.acionavel for o in reprovadas)


def test_nenhuma_aprovada_tem_componente_critico_fraco():
    criticos = {"gatilho", "risco_retorno", "suporte_resistencia"}
    for op in APROVADAS:
        for c in op.score_detalhado.componentes:
            if c.chave in criticos:
                assert c.nota >= 20, f"{op.symbol}: {c.nome} em {c.nota}"


def test_rr_minimo_e_respeitado():
    exigente = OpportunityEngine(config=ConfigOportunidade(rr_minimo=99.0))
    assert [o for o in _oportunidades(exigente, limite=800) if o.acionavel] == []


def test_o_alvo_nao_atravessa_a_primeira_zona_contraria():
    for op in APROVADAS[:10]:
        estrutura = op.score_detalhado.componente("suporte_resistencia")
        assert "ALVO passa por dentro" not in estrutura.leitura


# ---------------------------------------------------------------------------
# transparencia e avisos
# ---------------------------------------------------------------------------


def test_toda_oportunidade_avaliada_carrega_o_score_aberto():
    for op in TODAS[::40]:
        if op.entry:
            assert op.score_detalhado is not None
            assert len(op.score_detalhado.componentes) == 11


def test_avisos_apontam_componentes_fracos():
    com_aviso = [o for o in TODAS if o.warnings]

    assert com_aviso
    assert any("fraco" in a or "risco/retorno" in a or "contexto" in a
               for o in com_aviso for a in o.warnings)


def test_motivos_citam_os_componentes_que_mais_pesaram():
    op = APROVADAS[0]

    assert any("/100" in r for r in op.reasons)


def test_pesos_customizados_mudam_o_score_da_mesma_situacao():
    outros = PESOS_PADRAO.atualizar(fibonacci=5.0, tendencia=0.1)
    engine = OpportunityEngine(pesos=outros)
    mtf = engine.alimentar(SERIE)
    padrao = OpportunityEngine()
    mtf_padrao = padrao.alimentar(SERIE)

    vistas = list(mtf.replay())[::60]
    diferentes = 0
    for vista in vistas:
        a = engine.avaliar(vista, "PETR4")
        b = padrao.avaliar(mtf_padrao.em(vista.instante), "PETR4")
        if a.entry and abs(a.score - b.score) > 0.1:
            diferentes += 1
    assert diferentes > 0


def test_config_invalida_e_recusada():
    with pytest.raises(ValueError):
        ConfigOportunidade(score_minimo=150)
    with pytest.raises(ValueError):
        ConfigOportunidade(rr_minimo=0)
    with pytest.raises(ValueError):
        ConfigOportunidade(expiracao_candles_gatilho=0)
