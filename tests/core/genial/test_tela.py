"""A tela BOLETA GENIAL."""

from __future__ import annotations

import pytest

from cashinho.core.genial import (
    SELO,
    TicketGenerator,
    bloco_boleta,
    bloco_para_copiar,
    faixa_nao_envia,
    pagina,
    painel_resumo,
    pendentes,
    resumo_uma_linha,
    secao_condicoes,
    secao_pendencias,
)
from cashinho.core.oportunidade.estados import EstadoOportunidade

from .factories import oportunidade

GERADOR = TicketGenerator()
TICKET = GERADOR.gerar(oportunidade(), quantidade=600, preco_atual=31.02)
NAO_GERADO = GERADOR.gerar(oportunidade(estado=EstadoOportunidade.REJEITADO), quantidade=600)


# --- o titulo e o aviso -------------------------------------------------------


def test_a_tela_se_chama_boleta_genial():
    assert "BOLETA GENIAL" in pagina(TICKET)


def test_a_tela_avisa_que_nao_envia_ordem():
    texto = pagina(TICKET)

    assert "NAO ENVIA ORDEM" in texto
    assert "DIGITACAO MANUAL" in texto


def test_a_faixa_de_aviso_e_destacada():
    assert "╔" in faixa_nao_envia()


# --- os campos ------------------------------------------------------------------


def test_a_tela_mostra_os_nove_campos():
    texto = pagina(TICKET)

    for campo in ("Ativo", "Quantidade", "Validade", "Preco", "A Mercado",
                  "OCO", "Gain", "Loss", "Offset"):
        assert campo in texto


def test_campos_a_confirmar_levam_marca():
    texto = bloco_boleta(TICKET.entrada)

    assert "⚠" in texto


def test_as_observacoes_podem_ser_escondidas():
    com = bloco_boleta(TICKET.entrada, mostrar_observacoes=True)
    sem = bloco_boleta(TICKET.entrada, mostrar_observacoes=False)

    assert len(sem.splitlines()) < len(com.splitlines())
    assert "Ativo" in sem


# --- o resumo da operacao ---------------------------------------------------------


def test_o_resumo_mostra_os_itens_pedidos():
    texto = painel_resumo(TICKET.resumo)

    for rotulo in ("entrada", "stop", "alvo", "risco", "retorno potencial",
                   "R:R", "score", "status", "setup", "timestamp"):
        assert rotulo in texto


def test_o_resumo_mostra_o_status_da_oportunidade():
    assert "SETUP APROVADO" in painel_resumo(TICKET.resumo)


# --- as condicoes obrigatorias ------------------------------------------------------


def test_a_tela_traz_entrar_somente_se():
    texto = pagina(TICKET)

    assert "ENTRAR SOMENTE SE:" in texto


def test_a_tela_traz_cancelar_a_operacao_se():
    texto = pagina(TICKET)

    assert "CANCELAR A OPERACAO SE:" in texto


def test_as_duas_secoes_listam_condicoes():
    texto = secao_condicoes(TICKET)
    antes, depois = texto.split("CANCELAR A OPERACAO SE:")

    assert antes.count("   · ") >= 2
    assert depois.count("   · ") >= 2


# --- as pendencias --------------------------------------------------------------------


def test_a_tela_lista_o_que_falta_confirmar():
    texto = pagina(TICKET)

    assert SELO in texto
    assert "nada disto foi verificado" in texto


def test_cada_pendencia_diz_o_que_foi_assumido_e_o_que_conferir():
    texto = secao_pendencias(TICKET.pendencias)

    assert "assumido:" in texto
    assert "confirmar:" in texto


def test_o_offset_esta_entre_as_pendencias():
    texto = secao_pendencias(TICKET.pendencias)

    assert "Offset" in texto
    assert "MAIS AMBIGUO" in texto


def test_sem_pendencias_a_secao_some():
    assert secao_pendencias([]) == ""


# --- copiar para a plataforma ------------------------------------------------------------


def test_o_bloco_de_copia_traz_so_campo_e_valor():
    texto = bloco_para_copiar(TICKET)

    assert "⚠" not in texto
    assert "assumido" not in texto
    assert "Ativo" in texto and "PETR4" in texto
    assert "[Compra Stop] entrada" in texto


def test_o_bloco_de_copia_alinha_os_rotulos():
    """Os valores comecam todos na mesma coluna - da para bater o olho e digitar."""
    campos = TICKET.entrada.campos
    largura = max(len(c.rotulo) for c in campos)
    linhas = [l for l in TICKET.entrada.para_copiar().splitlines() if l.strip()]

    assert len(linhas) == len(campos)
    for linha in linhas:
        assert linha[:largura].rstrip()          # rotulo a esquerda
        assert linha[largura:largura + 2] == "  "  # duas colunas de separacao
        assert linha[largura + 2:].strip()       # valor comeca sempre no mesmo lugar


def test_boleta_nao_gerada_nao_tem_bloco_de_copia():
    assert bloco_para_copiar(NAO_GERADO) == ""


# --- boleta nao gerada -------------------------------------------------------------------


def test_a_tela_explica_quando_nao_ha_boleta():
    texto = pagina(NAO_GERADO)

    assert "BOLETA NAO GERADA" in texto
    assert "SETUP REJEITADO" in texto
    assert SELO in texto  # as pendencias continuam visiveis


def test_cores_sao_opcionais():
    assert "\033[" not in pagina(TICKET, cores=False)
    assert "\033[" in pagina(TICKET, cores=True)


def test_resumo_cabe_em_uma_linha():
    linha = resumo_uma_linha(TICKET)

    assert "\n" not in linha
    assert "PETR4" in linha and "R:R" in linha
