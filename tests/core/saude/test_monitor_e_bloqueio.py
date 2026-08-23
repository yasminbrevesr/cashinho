"""O monitor, e a regra que sai da tela e vira trava."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.core.broker.base import broker_base
from cashinho.core.broker.modelos import OrderStatus, OrderType
from cashinho.core.saude import (
    BrokerComSaude,
    ConfigSaude,
    EstadoDeSaude,
    LimiaresSaude,
    Modo,
    MonitorDeSaude,
    OperacaoBloqueadaPorSaudeError,
    Telemetria,
)

from .factories import AGORA, monitor, ordem, paper, risco, telemetria


# --- o painel completo -------------------------------------------------------


def test_o_painel_tem_os_sete_componentes_pedidos():
    saude = monitor().verificar()
    nomes = [c.nome for c in saude.componentes]

    assert nomes == ["Market Data", "Database", "Scanner", "Paper Broker",
                     "News", "Backtest Engine", "Risk Manager"]


def test_o_painel_mostra_tudo_o_que_foi_pedido():
    m = monitor(t=telemetria(AGORA, scanner=0), broker=paper(), risco=risco())
    m.registrar_analise(AGORA - timedelta(minutes=2))
    saude = m.verificar()

    md = saude.componente("market_data")
    assert md.ultimo_timestamp is not None      # ultimo timestamp recebido
    assert md.latencia_ms is not None           # latencia
    assert saude.erros == ()                    # erros recentes
    assert saude.modo is Modo.ANALISE           # modo atual
    assert saude.kill_switch_ativo is False     # kill switch
    assert saude.ultima_analise is not None     # horario da ultima analise


def test_o_estado_geral_e_o_do_pior_componente():
    saude = monitor().verificar()

    assert saude.estado_geral is EstadoDeSaude.OFFLINE  # ha componentes sem conexao


def test_o_modo_atual_aparece_no_retrato():
    assert monitor(modo=Modo.PAPER).verificar().modo is Modo.PAPER


def test_a_ultima_analise_e_registrada():
    m = monitor()
    m.registrar_analise(AGORA - timedelta(minutes=7))

    assert m.verificar().ultima_analise == AGORA - timedelta(minutes=7)


def test_o_retrato_serializa():
    import json

    dados = json.loads(json.dumps(monitor(broker=paper(), risco=risco())
                                  .verificar().para_dict()))
    assert set(dados) >= {"timestamp", "estado_geral", "modo", "kill_switch",
                          "ultima_analise", "bloqueia_novas_operacoes", "componentes"}


# --- a regra: Market Data fora do ar bloqueia -----------------------------------


def test_market_data_online_libera_operacoes():
    saude = monitor(t=telemetria(AGORA, market_data_min=1)).verificar()

    assert saude.bloqueia_novas_operacoes is False
    assert saude.rotulo_operacao == "OPERACOES LIBERADAS"


def test_market_data_desatualizado_bloqueia_operacoes():
    saude = monitor(t=telemetria(AGORA, market_data_min=25)).verificar()

    assert saude.bloqueia_novas_operacoes is True
    assert "Market Data OFFLINE" in saude.bloqueios[0]


def test_market_data_sem_dado_nenhum_bloqueia():
    t = Telemetria(relogio=lambda: AGORA)

    assert monitor(t=t).verificar().bloqueia_novas_operacoes is True


def test_componente_nao_critico_fora_do_ar_nao_bloqueia():
    """News ou Scanner caidos nao param a operacao - Market Data para."""
    saude = monitor(t=telemetria(AGORA, market_data_min=1)).verificar()

    assert any(c.estado is EstadoDeSaude.OFFLINE for c in saude.componentes)
    assert saude.bloqueia_novas_operacoes is False


def test_degradado_nao_bloqueia_por_padrao():
    """Pequeno atraso e' o normal em feed gratuito."""
    saude = monitor(t=telemetria(AGORA, market_data_min=5)).verificar()

    assert saude.componente("market_data").estado is EstadoDeSaude.DEGRADED
    assert saude.bloqueia_novas_operacoes is False


def test_da_para_exigir_market_data_impecavel():
    config = ConfigSaude(bloqueia_em=(EstadoDeSaude.OFFLINE, EstadoDeSaude.DEGRADED))
    saude = monitor(t=telemetria(AGORA, market_data_min=5), config=config).verificar()

    assert saude.bloqueia_novas_operacoes is True


def test_permite_novas_operacoes_e_o_inverso_do_bloqueio():
    m = monitor(t=telemetria(AGORA, market_data_min=25))

    assert m.permite_novas_operacoes() is False
    assert m.verificar().bloqueia_novas_operacoes is True


# --- kill switch ------------------------------------------------------------------


def test_kill_switch_do_risco_aparece_e_bloqueia():
    r = risco()
    r.acionar_kill_switch("perda diaria")
    saude = monitor(t=telemetria(AGORA, market_data_min=1), risco=r).verificar()

    assert saude.kill_switch_ativo is True
    assert saude.bloqueia_novas_operacoes is True
    assert any("KILL SWITCH" in b for b in saude.bloqueios)


def test_kill_switch_do_paper_broker_tambem_aparece():
    """Sao dois lugares que param o robo; o painel mostra os dois."""
    broker = paper()
    broker.kill_switch_ativo = True
    broker.kill_switch_motivo = "botao da tela"

    saude = monitor(t=telemetria(AGORA, market_data_min=1), broker=broker).verificar()

    assert saude.kill_switch_ativo is True
    assert "botao da tela" in saude.para_dict()["kill_switch"]["motivo"]


def test_sem_kill_switch_o_campo_fica_livre():
    saude = monitor(t=telemetria(AGORA, market_data_min=1), risco=risco()).verificar()

    assert saude.kill_switch_ativo is False
    assert saude.para_dict()["kill_switch"] is None


# --- a trava na porta da corretora ------------------------------------------------------


def guardado(minutos_de_atraso: float = 1.0, **campos):
    broker = paper()
    m = monitor(t=telemetria(AGORA, market_data_min=minutos_de_atraso), broker=broker)
    return BrokerComSaude(broker, m, **campos), broker


def test_ordem_nova_passa_com_dado_fresco():
    guarda, broker = guardado(1)

    resposta = guarda.place_order(ordem())

    assert resposta.status is OrderStatus.EXECUTADA
    assert len(broker.get_orders()) == 1


def test_ordem_nova_e_recusada_com_dado_velho():
    guarda, broker = guardado(30)

    resposta = guarda.place_order(ordem())

    assert resposta.status is OrderStatus.REJEITADA
    assert "bloqueada" in resposta.motivo
    assert "Market Data OFFLINE" in resposta.motivo
    assert broker.get_orders() == []


def test_a_ordem_bloqueada_fica_registrada():
    guarda, _ = guardado(30)
    guarda.place_order(ordem())

    assert len(guarda.bloqueadas) == 1


def test_da_para_pedir_que_o_bloqueio_levante():
    guarda, _ = guardado(30, levantar=True)

    with pytest.raises(OperacaoBloqueadaPorSaudeError, match="Market Data"):
        guarda.place_order(ordem())


def test_saida_de_posicao_passa_mesmo_com_o_feed_caido():
    """Trava que impede de sair de posicao aberta e' pior que trava nenhuma."""
    guarda, broker = guardado(1)
    guarda.place_order(ordem(compra=True))

    guarda.monitor.telemetria.sucesso(
        "market_data", dado_em=AGORA - timedelta(minutes=45))

    saida = guarda.place_order(ordem(compra=False))

    assert saida.status is OrderStatus.EXECUTADA


def test_ordem_de_protecao_passa_mesmo_bloqueado():
    guarda, broker = guardado(1)
    guarda.place_order(ordem(compra=True))
    guarda.monitor.telemetria.sucesso(
        "market_data", dado_em=AGORA - timedelta(minutes=45))

    stop = guarda.place_order(ordem(compra=False, tipo=OrderType.STOP_LOSS,
                                    preco_disparo=29.0))

    assert stop.status is not OrderStatus.REJEITADA


def test_a_trava_de_saude_empilha_com_as_outras():
    from cashinho.core.broker.risco import BrokerComRisco

    broker = paper()
    m = monitor(t=telemetria(AGORA, market_data_min=1), broker=broker)
    empilhado = BrokerComSaude(BrokerComRisco(broker, risco()), m)

    assert broker_base(empilhado) is broker
    assert "saude" in empilhado.nome


def test_o_resto_da_interface_passa_direto():
    guarda, broker = guardado(30)

    assert guarda.get_balance().patrimonio == broker.get_balance().patrimonio
    assert guarda.get_positions() == []
    assert guarda.get_trades() == []
    assert guarda.simulado is True
