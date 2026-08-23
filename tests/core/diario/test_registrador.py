"""Registro automatico a partir do Paper Broker."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from cashinho.core.backtest.costs import SEM_CUSTOS
from cashinho.core.broker import ConfigPaper, Order, OrderType, PaperBroker
from cashinho.core.diario import BrokerComDiario, ContextoDeEntrada, DiarioDeTrades
from cashinho.models import BRT, Candle, Direction

AGORA = datetime(2026, 8, 20, 11, 5, tzinfo=BRT)


def _broker(arquivo=None):
    relogio = {"t": AGORA}
    paper = PaperBroker(ConfigPaper(capital_inicial=100_000.0, custos=SEM_CUSTOS),
                        lambda: relogio["t"])
    paper.atualizar_preco("PETR4", 31.00)
    return BrokerComDiario(paper, DiarioDeTrades(), arquivo=arquivo), paper, relogio


def _abre_e_fecha(b, paper, relogio, saida=31.60, quantidade=300):
    b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, quantidade))
    relogio["t"] = AGORA + timedelta(minutes=42)
    paper.atualizar_preco("PETR4", saida)
    b.place_order(Order("PETR4", Direction.SHORT, OrderType.MARKET, quantidade))


# --- automatico ------------------------------------------------------------------


def test_a_operacao_encerrada_vira_registro_sozinha():
    b, paper, relogio = _broker()
    _abre_e_fecha(b, paper, relogio)

    assert len(b.diario) == 1
    r = b.diario.registros[0]
    assert r.symbol == "PETR4"
    assert r.quantidade == 300
    assert r.resultado > 0


def test_posicao_ainda_aberta_nao_gera_registro():
    b, paper, relogio = _broker()
    b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 300))

    assert len(b.diario) == 0
    assert b.get_positions()


def test_o_registro_traz_o_que_a_corretora_sabe():
    b, paper, relogio = _broker()
    _abre_e_fecha(b, paper, relogio, saida=31.60)
    r = b.diario.registros[0]

    assert r.entrada == pytest.approx(31.00)
    assert r.saida == pytest.approx(31.60)
    assert r.aberta_em == AGORA
    assert r.fechada_em == AGORA + timedelta(minutes=42)
    assert r.motivo_saida == "encerrada a mercado"


def test_o_contexto_completa_a_outra_metade():
    b, paper, relogio = _broker()
    b.anotar_contexto("PETR4", stop=30.70, alvo=31.60, setup="pullback",
                      motivo_entrada=("camadas alinhadas",), observacao="teste")
    _abre_e_fecha(b, paper, relogio)
    r = b.diario.registros[0]

    assert r.setup == "pullback"
    assert r.stop == pytest.approx(30.70)
    assert r.rr == pytest.approx(2.0)
    assert r.motivo_entrada == ("camadas alinhadas",)
    assert r.observacao == "teste"


def test_sem_contexto_o_registro_entra_incompleto_e_nao_se_perde():
    """Melhor um diario sem o porque do que um trade nao registrado."""
    b, paper, relogio = _broker()
    _abre_e_fecha(b, paper, relogio)
    r = b.diario.registros[0]

    assert len(b.diario) == 1
    assert r.setup == ""
    assert r.risco == 0.0
    assert r.resultado != 0


def test_stop_loss_registra_o_motivo_da_saida():
    b, paper, relogio = _broker()
    b.anotar_contexto("PETR4", stop=30.70)
    b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 300))
    b.place_order(Order("PETR4", Direction.SHORT, OrderType.STOP_LOSS, 300,
                        preco_disparo=30.70))
    relogio["t"] = AGORA + timedelta(minutes=10)
    b.processar("PETR4", Candle(relogio["t"], 31.0, 31.1, 30.40, 30.60, 1e5))

    assert b.diario.registros[0].motivo_saida == "stop acionado"


def test_varias_operacoes_entram_em_ordem():
    b, paper, relogio = _broker()
    for i, saida in enumerate((31.60, 30.80)):
        relogio["t"] = AGORA + timedelta(hours=i)
        paper.atualizar_preco("PETR4", 31.00)
        b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 100))
        relogio["t"] = AGORA + timedelta(hours=i, minutes=20)
        paper.atualizar_preco("PETR4", saida)
        b.place_order(Order("PETR4", Direction.SHORT, OrderType.MARKET, 100))

    assert len(b.diario) == 2
    assert b.diario.registros[0].venceu
    assert b.diario.registros[1].perdeu


def test_a_mesma_operacao_nao_e_registrada_duas_vezes():
    b, paper, relogio = _broker()
    _abre_e_fecha(b, paper, relogio)

    b.sincronizar()
    b.sincronizar()

    assert len(b.diario) == 1


# --- contexto persistente -----------------------------------------------------------


def test_o_contexto_vai_e_volta_de_dicionario():
    b, paper, relogio = _broker()
    b.anotar_contexto("PETR4", stop=30.70, alvo=31.60, setup="pullback",
                      motivo_entrada=("motivo",))

    dados = json.loads(json.dumps(b.contextos_para_dict()))
    outro, _, _ = _broker()
    outro.carregar_contextos(dados)

    assert outro.contexto("PETR4").stop == pytest.approx(30.70)
    assert outro.contexto("PETR4").setup == "pullback"


def test_contexto_recarregado_completa_o_registro():
    """O caso do CLI: cada comando roda num processo novo."""
    primeiro, _, _ = _broker()
    primeiro.anotar_contexto("PETR4", stop=30.70, alvo=31.60, setup="pullback")
    dados = primeiro.contextos_para_dict()

    b, paper, relogio = _broker()
    b.carregar_contextos(dados)
    _abre_e_fecha(b, paper, relogio)

    assert b.diario.registros[0].setup == "pullback"
    assert b.diario.registros[0].rr == pytest.approx(2.0)


def test_contexto_a_partir_de_uma_oportunidade():
    from cashinho.core.oportunidade.estados import EstadoOportunidade
    from cashinho.core.oportunidade.modelos import Opportunity

    op = Opportunity(
        symbol="PETR4", timestamp=AGORA, direction=Direction.LONG, setup="pullback mtf",
        score=81.0, entry=31.0, stop=30.7, target=31.6, risk_reward=2.0,
        timeframe_context="60m", timeframe_trend="15m", timeframe_setup="5m",
        timeframe_trigger="1m", reasons=("camadas alinhadas", "volume"),
        warnings=(), invalidation="-", expires_at=None,
        estado=EstadoOportunidade.APROVADO,
    )
    contexto = ContextoDeEntrada.de_oportunidade(op)

    assert contexto.setup == "pullback mtf"
    assert contexto.score == 81.0
    assert contexto.timeframe_setup == "5m"
    assert contexto.motivo_entrada == ("camadas alinhadas", "volume")


# --- arquivo ---------------------------------------------------------------------------


def test_o_registro_e_gravado_no_arquivo_na_hora(tmp_path):
    arquivo = tmp_path / "diario.jsonl"
    b, paper, relogio = _broker(arquivo=arquivo)
    _abre_e_fecha(b, paper, relogio)

    assert arquivo.exists()
    linhas = [l for l in arquivo.read_text().splitlines() if l.strip()]
    assert len(linhas) == 1
    assert json.loads(linhas[0])["symbol"] == "PETR4"


# --- interface preservada ------------------------------------------------------------------


def test_o_wrapper_continua_sendo_um_broker():
    from cashinho.core.broker import Broker

    b, _, _ = _broker()
    assert isinstance(b, Broker)
    for metodo in ("place_order", "cancel_order", "get_orders", "get_positions", "get_balance"):
        assert callable(getattr(b, metodo))


def test_o_wrapper_repassa_saldo_e_posicoes():
    b, paper, relogio = _broker()
    b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 300))

    assert b.get_balance().patrimonio == paper.get_balance().patrimonio
    assert len(b.get_positions()) == 1


def test_empilhado_com_o_risco_tambem_registra():
    from cashinho.core.broker import BrokerComRisco
    from cashinho.core.risk import RiskConfig, RiskManager, RiskState

    paper = PaperBroker(ConfigPaper(capital_inicial=100_000.0, custos=SEM_CUSTOS),
                        lambda: AGORA)
    paper.atualizar_preco("PETR4", 31.00)
    risco = RiskManager(RiskConfig(capital=100_000.0, exposicao_max_por_ativo_pct=100.0,
                                   exposicao_max_total_pct=100.0),
                        RiskState(capital_inicial=100_000.0))
    b = BrokerComDiario(BrokerComRisco(paper, risco), DiarioDeTrades())
    b.anotar_contexto("PETR4", stop=30.70)

    b.place_order(Order("PETR4", Direction.LONG, OrderType.MARKET, 300,
                        stop_referencia=30.70))
    paper.atualizar_preco("PETR4", 31.60)
    b.place_order(Order("PETR4", Direction.SHORT, OrderType.MARKET, 300))

    assert len(b.diario) == 1
    assert b.diario.registros[0].resultado > 0


def test_um_diario_vazio_passado_no_construtor_e_o_mesmo_objeto():
    """DiarioDeTrades define __len__: vazio e' falsy, e `x or Y()` o trocaria."""
    meu = DiarioDeTrades()
    assert len(meu) == 0 and not meu  # falsy de proposito

    paper = PaperBroker(ConfigPaper(capital_inicial=100_000.0, custos=SEM_CUSTOS),
                        lambda: AGORA)
    b = BrokerComDiario(paper, meu)

    assert b.diario is meu


def test_o_registro_cai_no_diario_que_foi_passado():
    meu = DiarioDeTrades()
    b, paper, relogio = _broker()
    b.diario = meu
    b._registradas = 0
    _abre_e_fecha(b, paper, relogio)

    assert len(meu) == 1
