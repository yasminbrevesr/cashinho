"""O Ticket Generator: tipos, campos e o que ele NAO faz."""

from __future__ import annotations

import json

import pytest

from cashinho.core.genial import (
    ConfigTicket,
    PapelDaBoleta,
    TicketGenerator,
    TipoBoleta,
)
from cashinho.core.oportunidade.estados import EstadoOportunidade
from cashinho.models import Direction

from .factories import AGORA, decisao, oportunidade

GERADOR = TicketGenerator()


def _ticket(op=None, preco_atual=None, quantidade=600, **kwargs):
    op = op or oportunidade(**kwargs)
    return GERADOR.gerar(op, quantidade=quantidade, preco_atual=preco_atual)


# --- o que este modulo NAO faz -------------------------------------------------


def test_o_gerador_nao_envia_ordem():
    assert TicketGenerator.envia_ordem is False

    metodos = {m for m in dir(TicketGenerator) if not m.startswith("_")}
    assert not (metodos & {"enviar", "send", "executar", "transmitir", "place_order"})


def test_o_modulo_nao_importa_nada_de_rede():
    """Sem cliente HTTP e sem socket: este modulo nao tem como enviar nada.

    A checagem e' na arvore de sintaxe, nao no texto - o docstring FALA de
    api e token justamente para dizer que nao os usa.
    """
    import ast
    import inspect

    from cashinho.core.genial import gerador, modelos, regras, view

    proibidos = {"http", "httpx", "requests", "urllib", "urllib3", "socket",
                 "aiohttp", "websocket", "ssl", "ftplib", "smtplib"}

    for modulo in (gerador, modelos, regras, view):
        arvore = ast.parse(inspect.getsource(modulo))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = [a.name.split(".")[0] for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [(no.module or "").split(".")[0]]
            else:
                continue
            for nome in nomes:
                assert nome not in proibidos, (
                    f"{modulo.__name__} importa {nome}: este modulo nao pode falar com a rede"
                )


def test_nenhuma_funcao_publica_sugere_envio():
    import inspect

    from cashinho.core.genial import gerador

    publicas = {
        nome for nome, _ in inspect.getmembers(gerador, inspect.isfunction)
        if not nome.startswith("_")
    }
    publicas |= {m for m in dir(gerador.TicketGenerator) if not m.startswith("_")}

    proibidas = {"enviar", "send", "post", "transmitir", "executar", "roteiar"}
    assert not (publicas & proibidas)


def test_o_payload_declara_que_nao_envia():
    assert _ticket().para_dict()["envia_ordem"] is False


# --- so gera para oportunidade aprovada -------------------------------------------


@pytest.mark.parametrize("estado", [
    EstadoOportunidade.AGUARDANDO_GATILHO,
    EstadoOportunidade.REJEITADO,
    EstadoOportunidade.NAO_OPERAR,
    EstadoOportunidade.EXPIRADO,
])
def test_oportunidade_nao_aprovada_nao_vira_boleta(estado):
    t = _ticket(estado=estado)

    assert t.gerado is False
    assert estado.value in t.motivo
    assert t.boletas == ()


def test_decisao_de_risco_recusada_nao_vira_boleta():
    op = oportunidade()
    rm_decisao = decisao(op, capital=100.0)  # capital pequeno demais
    t = GERADOR.gerar(op, rm_decisao)

    assert t.gerado is False
    assert "Risk Manager recusou" in t.motivo


def test_sem_quantidade_nao_gera():
    t = GERADOR.gerar(oportunidade())

    assert t.gerado is False
    assert "sem quantidade" in t.motivo


def test_a_quantidade_vem_da_decisao_de_risco():
    op = oportunidade()
    d = decisao(op)
    t = GERADOR.gerar(op, d)

    assert t.gerado is True
    assert t.resumo.quantidade == d.position_size


# --- escolha do tipo de boleta ----------------------------------------------------


def test_entrada_acima_do_preco_vira_compra_stop():
    t = _ticket(preco_atual=31.02, entry=31.15)

    assert t.entrada.tipo is TipoBoleta.COMPRA_STOP
    assert "rompimento" in t.entrada.explicacao


def test_entrada_abaixo_do_preco_vira_compra_limitada():
    t = _ticket(preco_atual=31.02, entry=30.90)

    assert t.entrada.tipo is TipoBoleta.COMPRA
    assert "limitada" in t.entrada.explicacao


def test_venda_abaixo_do_preco_vira_venda_stop():
    op = oportunidade(direction=Direction.SHORT, entry=30.80, stop=31.20, target=30.00)
    t = GERADOR.gerar(op, quantidade=600, preco_atual=31.00)

    assert t.entrada.tipo is TipoBoleta.VENDA_STOP


def test_venda_acima_do_preco_vira_venda_limitada():
    op = oportunidade(direction=Direction.SHORT, entry=31.20, stop=31.60, target=30.40)
    t = GERADOR.gerar(op, quantidade=600, preco_atual=31.00)

    assert t.entrada.tipo is TipoBoleta.VENDA


def test_os_quatro_tipos_pedidos_existem():
    assert {t.value for t in TipoBoleta} == {"Compra", "Compra Stop", "Venda", "Venda Stop"}


# --- campos ---------------------------------------------------------------------------


def test_a_boleta_tem_os_nove_campos_pedidos():
    campos = {c.rotulo for c in _ticket().entrada.campos}

    for pedido in ("Ativo", "Quantidade", "Validade", "Preco", "A Mercado", "OCO",
                   "Gain", "Loss", "Offset"):
        assert pedido in campos


def test_boleta_stop_tem_disparo_e_limite_separados():
    t = _ticket(preco_atual=31.02, entry=31.15)
    entrada = t.entrada

    assert entrada.valor("Preco de disparo") == "31,15"
    assert entrada.valor("Preco") == "31,17"  # limite dois ticks acima


def test_o_limite_da_venda_stop_fica_abaixo_do_disparo():
    op = oportunidade(direction=Direction.SHORT, entry=30.80, stop=31.20, target=30.00)
    entrada = GERADOR.gerar(op, quantidade=600, preco_atual=31.00).entrada

    assert entrada.campo("Preco").valor_bruto < entrada.campo("Preco de disparo").valor_bruto


def test_valores_saem_no_formato_brasileiro_sem_cifrao():
    """A boleta nao aceita 'R$' - o valor tem que estar pronto para colar."""
    t = _ticket(preco_atual=31.02, entry=31.15)

    assert t.entrada.valor("Preco de disparo") == "31,15"
    assert "R$" not in t.entrada.valor("Preco de disparo")


def test_precos_sao_arredondados_ao_tick():
    op = oportunidade(entry=31.1537, stop=30.7212, target=32.0189)
    t = GERADOR.gerar(op, quantidade=600, preco_atual=31.00)

    assert t.resumo.entrada == pytest.approx(31.15)
    assert t.resumo.stop == pytest.approx(30.72)


def test_a_protecao_sai_como_oco_com_gain_e_loss():
    t = _ticket()
    oco = t.boleta(PapelDaBoleta.OCO)

    assert oco is not None
    assert oco.valor("OCO") == "sim"
    assert oco.valor("Gain") == "32,01"
    assert oco.valor("Loss") == "30,72"
    assert oco.tipo is TipoBoleta.VENDA  # protege uma compra


def test_a_protecao_de_uma_venda_e_boleta_de_compra():
    op = oportunidade(direction=Direction.SHORT, entry=30.80, stop=31.20, target=30.00)
    oco = GERADOR.gerar(op, quantidade=600, preco_atual=31.00).boleta(PapelDaBoleta.OCO)

    assert oco.tipo is TipoBoleta.COMPRA


def test_protecao_pode_sair_em_boletas_separadas():
    gerador = TicketGenerator(ConfigTicket(usar_oco_para_protecao=False))
    t = gerador.gerar(oportunidade(), quantidade=600, preco_atual=31.00)

    assert t.boleta(PapelDaBoleta.STOP) is not None
    assert t.boleta(PapelDaBoleta.ALVO) is not None
    assert t.boleta(PapelDaBoleta.OCO) is None
    assert t.boleta(PapelDaBoleta.STOP).tipo is TipoBoleta.VENDA_STOP


def test_o_offset_e_configuravel():
    gerador = TicketGenerator(ConfigTicket(ticks_de_offset=5))
    t = gerador.gerar(oportunidade(), quantidade=600, preco_atual=31.02)

    assert t.entrada.valor("Offset") == "0,05"


# --- resumo da operacao -------------------------------------------------------------------


def test_o_resumo_traz_os_dez_itens_pedidos():
    r = _ticket().resumo

    assert r.ativo == "PETR4"
    assert r.entrada > 0 and r.stop > 0 and r.alvo > 0
    assert r.risco_monetario > 0 and r.retorno_potencial > 0
    assert r.rr > 0
    assert r.score == 78.4
    assert r.setup
    assert r.status == "SETUP APROVADO"
    assert r.timestamp == AGORA


def test_risco_e_retorno_batem_com_a_quantidade():
    t = _ticket(quantidade=600)
    r = t.resumo

    assert r.risco_monetario == pytest.approx(abs(r.entrada - r.stop) * 600)
    assert r.retorno_potencial == pytest.approx(abs(r.alvo - r.entrada) * 600)
    assert r.rr == pytest.approx(r.retorno_potencial / r.risco_monetario)


# --- condicoes obrigatorias ------------------------------------------------------------------


def test_entrar_somente_se_nunca_vem_vazio():
    t = _ticket()

    assert t.entrar_somente_se
    assert len(t.entrar_somente_se) >= 3


def test_cancelar_se_nunca_vem_vazio():
    t = _ticket()

    assert t.cancelar_se
    assert any("30,72" in c for c in t.cancelar_se)


def test_a_condicao_de_entrada_combina_com_o_tipo_da_boleta():
    """Boleta stop fala em romper; boleta limitada fala em recuar."""
    stop = _ticket(preco_atual=31.02, entry=31.15)
    limitada = _ticket(preco_atual=31.02, entry=30.90)

    assert "negociar acima" in stop.entrar_somente_se[0]
    assert stop.entrada.tipo is TipoBoleta.COMPRA_STOP

    assert "recuar ate" in limitada.entrar_somente_se[0]
    assert limitada.entrada.tipo is TipoBoleta.COMPRA


def test_as_condicoes_citam_as_camadas_e_a_validade():
    t = _ticket()

    assert any("60m" in c for c in t.entrar_somente_se)
    assert any("12:40" in c for c in t.entrar_somente_se)
    assert any("12:40" in c for c in t.cancelar_se)


def test_sem_leitura_as_condicoes_continuam_existindo():
    t = _ticket(com_leitura=False)

    assert t.entrar_somente_se
    assert t.cancelar_se


# --- avisos e pendencias -----------------------------------------------------------------------


def test_o_primeiro_aviso_e_que_nao_envia_ordem():
    assert "NAO envia ordem" in _ticket().avisos[0]


def test_quantidade_fora_do_lote_vira_aviso():
    t = _ticket(quantidade=642)

    assert any("fracionario" in a for a in t.avisos)


def test_quantidade_no_lote_nao_gera_aviso_de_fracionario():
    t = _ticket(quantidade=600)

    assert not any("fracionario" in a for a in t.avisos)


def test_os_avisos_da_oportunidade_sao_repassados():
    t = _ticket()

    assert any("pouca margem" in a for a in t.avisos)


def test_toda_boleta_carrega_as_pendencias_da_genial():
    t = _ticket()

    assert t.pendencias
    assert all(r.pendente for r in t.pendencias)


def test_o_ticket_serializa():
    dados = _ticket().para_dict()
    texto = json.dumps(dados)

    assert dados["gerado"] is True
    assert len(dados["boletas"]) == 2
    assert dados["entrar_somente_se"]
    assert '"pendencias"' in texto
