"""A pagina Risk Manager: status, configuracao e o aviso que importa."""

from __future__ import annotations

import json

import pytest

from cashinho.core.risk import faixa, pagina, resumo, ver_decisao
from cashinho.models import formata_dinheiro

from .factories import compra, config, gerente, perder


def test_pagina_mostra_trading_liberado_quando_esta_tudo_certo():
    rm = gerente()
    texto = pagina(rm.status(), rm.config)

    assert "TRADING LIBERADO" in texto
    assert "TRADING BLOQUEADO" not in texto


def test_pagina_mostra_trading_bloqueado_e_o_motivo():
    rm = gerente()
    rm.acionar_kill_switch("noticia relevante no meio do pregao")
    texto = pagina(rm.status(), rm.config)

    assert "TRADING BLOQUEADO" in texto
    assert "MOTIVO DO BLOQUEIO" in texto
    assert "noticia relevante" in texto


def test_faixa_de_status_e_destacada():
    rm = gerente()
    assert "TRADING LIBERADO" in faixa(rm.status())
    assert "╔" in faixa(rm.status())  # faixa larga, dificil de nao ver


def test_pagina_traz_os_cinco_ajustes_configuraveis():
    rm = gerente()
    texto = pagina(rm.status(), rm.config)

    assert "capital" in texto
    assert "risco por trade" in texto
    assert "perda maxima diaria" in texto
    assert "maximo de trades/dia" in texto
    assert "exposicao maxima" in texto


def test_pagina_mostra_o_uso_de_cada_limite():
    rm = gerente(config(capital=10_000.0, max_trades_dia=4, max_perdas_consecutivas=9,
                        perda_max_diaria_pct=100.0))
    perder(rm, 100.0)
    texto = pagina(rm.status(), rm.config)

    assert "perda do dia" in texto
    assert "trades no dia" in texto
    assert "drawdown" in texto
    assert "exposicao total" in texto
    assert "█" in texto  # barra de uso preenchida


def test_pagina_lista_as_posicoes_abertas():
    rm = gerente()
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    texto = pagina(rm.status(), rm.config)

    assert "PETR4" in texto
    assert "COMPRA" in texto

    vazio = pagina(gerente().status(), gerente().config)
    assert "nenhuma posicao aberta" in vazio


def test_pagina_avisa_como_o_kill_switch_desarma():
    rm = gerente(config(capital=10_000.0, perda_max_diaria_pct=3.0, max_trades_dia=50))
    perder(rm, 300.0)
    texto = pagina(rm.status(), rm.config)

    assert "kill switch" in texto
    assert "desarma no proximo pregao" in texto


def test_cores_sao_opcionais():
    rm = gerente()
    assert "\033[" not in pagina(rm.status(), rm.config, cores=False)
    assert "\033[" in pagina(rm.status(), rm.config, cores=True)


def test_decisao_aprovada_mostra_os_numeros_da_ordem():
    rm = gerente()
    texto = ver_decisao(rm.avaliar(compra(entrada=10.0, stop=9.5)))

    assert "APROVADO PELO RISCO" in texto
    assert "quantidade" in texto and "2000" in texto
    assert "risco monetario" in texto
    assert "exposicao resultante" in texto


def test_decisao_rejeitada_mostra_o_motivo_e_quantidade_zero():
    rm = gerente()
    rm.acionar_kill_switch("parado")
    texto = ver_decisao(rm.avaliar(compra()))

    assert "REJEITADO PELO RISCO" in texto
    assert "quantidade            0" in texto
    assert "parado" in texto


def test_resumo_cabe_em_uma_linha():
    rm = gerente()
    linha = resumo(rm.status())

    assert "\n" not in linha
    assert "TRADING LIBERADO" in linha


def test_status_serializa_para_uma_interface_grafica():
    rm = gerente()
    rm.abrir(rm.avaliar(compra(entrada=10.0, stop=9.5)))
    dados = rm.status().para_dict()

    texto = json.dumps(dados)  # nao pode ter objeto nao serializavel
    assert dados["rotulo"] == "TRADING LIBERADO"
    assert dados["posicoes"][0]["symbol"] == "PETR4"
    assert {l["nome"] for l in dados["limites"]} >= {"perda do dia", "trades no dia", "drawdown"}
    assert '"liberado": true' in texto


def test_decisao_serializa_com_os_cinco_campos():
    rm = gerente()
    dados = rm.avaliar(compra(entrada=10.0, stop=9.5)).para_dict()

    assert set(dados) >= {"allowed", "reason", "position_size", "monetary_risk", "portfolio_exposure"}


def test_perda_diaria_da_configuracao_bate_com_a_do_bloco_de_limites():
    """A pagina nao pode mostrar dois valores diferentes para o mesmo limite."""
    rm = gerente(config(capital=20_000.0, perda_max_diaria_pct=3.0, max_trades_dia=50,
                        max_perdas_consecutivas=50))
    perder(rm, 117.90)  # o patrimonio muda, o limite do dia nao

    status = rm.status()
    limite_do_bloco = next(l for l in status.limites if l.nome == "perda do dia").limite
    assert limite_do_bloco == pytest.approx(600.0)
    assert f"= {formata_dinheiro(limite_do_bloco)}" in pagina(status, rm.config)
