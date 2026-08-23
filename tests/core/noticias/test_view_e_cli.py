"""A secao NOTICIAS E EVENTOS e a linha de comando."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cashinho.core.noticias import (
    Disponibilidade,
    PoliticaDeEventos,
    Severidade,
    TipoDeEvento,
    ViesDirecional,
    agenda_indisponivel,
    linha_do_evento,
    pagina,
    secao_noticias,
)
from cashinho.core.noticias.__main__ import main

from .factories import AGORA, agenda, arquivo_de_eventos, bruto, evento


def avaliacao(a, symbol="PETR4"):
    return PoliticaDeEventos().avaliar(a, symbol, AGORA)


# --- a secao ------------------------------------------------------------------


def test_a_secao_tem_o_titulo():
    assert "NOTICIAS E EVENTOS" in secao_noticias(agenda([evento()]), AGORA)


def test_a_secao_lista_os_eventos_com_severidade_e_vies():
    texto = secao_noticias(agenda([evento(vies=ViesDirecional.BAIXA)]), AGORA, "PETR4")

    assert "RESULTADOS" in texto
    assert "PETR4" in texto
    assert "ALTA" in texto      # severidade
    assert "BAIXA" in texto     # vies


def test_evento_macro_aparece_como_mercado():
    texto = secao_noticias(
        agenda([evento(TipoDeEvento.PAYROLL, symbol="")]), AGORA, "PETR4")

    assert "MERCADO" in texto
    assert "PAYROLL" in texto


def test_fonte_ruim_mostra_noticias_indisponiveis():
    texto = secao_noticias(agenda_indisponivel("a fonte caiu"), AGORA)

    assert "NOTICIAS INDISPONIVEIS" in texto
    assert "a fonte caiu" in texto


def test_agenda_desatualizada_tambem_e_indisponivel():
    a = agenda([evento()], disponibilidade=Disponibilidade.DESATUALIZADA)

    assert "NOTICIAS INDISPONIVEIS" in secao_noticias(a, AGORA)


def test_agenda_vazia_disponivel_diz_que_nao_ha_evento():
    """Diferente de 'nao sabemos'."""
    texto = secao_noticias(agenda([]), AGORA, "PETR4")

    assert "NOTICIAS DISPONIVEIS" in texto
    assert "nenhum evento" in texto


def test_sem_agenda_a_secao_nao_fica_em_branco():
    texto = secao_noticias(None, AGORA)

    assert "NOTICIAS INDISPONIVEIS" in texto


def test_a_secao_mostra_o_efeito_na_operacao():
    a = agenda([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=20,
                       severidade=Severidade.CRITICA)])

    texto = secao_noticias(a, AGORA, "PETR4", avaliacao=avaliacao(a))

    assert "OPERACAO BLOQUEADA" in texto
    assert "score" in texto
    assert "posicao dividida" in texto


def test_a_secao_diz_que_noticia_nao_gera_ordem():
    texto = secao_noticias(agenda([evento()]), AGORA)

    assert "nunca gera compra ou venda" in texto


def test_registros_descartados_aparecem(tmp_path):
    from cashinho.core.noticias import FonteArquivo

    caminho = arquivo_de_eventos(tmp_path, [bruto(), bruto(tipo="boato")])
    a = FonteArquivo(caminho).carregar(AGORA)

    texto = secao_noticias(a, AGORA)

    assert "descartado" in texto


def test_evento_nao_confirmado_e_marcado():
    linha = linha_do_evento(evento(confirmado=False), AGORA)

    assert "a confirmar" in linha


def test_evento_distante_mostra_a_data_e_nao_horas():
    linha = linha_do_evento(evento(minutos=60 * 24 * 5), AGORA)

    assert "h (" not in linha


def test_a_pagina_aceita_cores():
    a = agenda([evento()])

    assert "\x1b[" in pagina(a, AGORA, "PETR4", cores=True)
    assert "\x1b[" not in pagina(a, AGORA, "PETR4", cores=False)


def test_a_secao_entra_na_tela_da_oportunidade():
    from cashinho.core.oportunidade.modelos import Opportunity
    from cashinho.core.oportunidade.view import pagina_oportunidade

    a = agenda([evento()])
    op = Opportunity(
        symbol="PETR4", timestamp=AGORA, direction=None, setup="teste", score=0.0,
        entry=None, stop=None, target=None, risk_reward=0.0,
        timeframe_context="60m", timeframe_trend="15m", timeframe_setup="5m",
        timeframe_trigger="1m", reasons=(), warnings=(), invalidation="-",
        expires_at=None, eventos=avaliacao(a),
    )

    assert "NOTICIAS E EVENTOS" in pagina_oportunidade(op)


# --- a linha de comando ---------------------------------------------------------


def test_cli_sem_arquivo_diz_noticias_indisponiveis(capsys):
    assert main(["--sem-cor"]) == 0
    saida = capsys.readouterr().out

    assert "NOTICIAS INDISPONIVEIS" in saida
    assert "--modelo" in saida


def test_cli_le_o_calendario(tmp_path, capsys):
    caminho = arquivo_de_eventos(tmp_path, [bruto()])

    assert main(["--arquivo", caminho, "--ativo", "PETR4",
                 "--instante", AGORA.isoformat(), "--sem-cor"]) == 0
    saida = capsys.readouterr().out

    assert "NOTICIAS DISPONIVEIS" in saida
    assert "RESULTADOS" in saida


def test_cli_em_json(tmp_path, capsys):
    caminho = arquivo_de_eventos(tmp_path, [bruto()])
    main(["--arquivo", caminho, "--instante", AGORA.isoformat(), "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["agenda"]["disponibilidade"] == "disponivel"
    evento_json = dados["agenda"]["eventos"][0]
    assert set(evento_json) >= {"event_type", "symbol", "timestamp", "severity",
                                "directional_bias", "confidence", "source"}


def test_cli_imprime_um_modelo_valido(capsys):
    assert main(["--modelo"]) == 0
    modelo = json.loads(capsys.readouterr().out)

    assert "atualizado_em" in modelo and "eventos" in modelo
    assert "_modelo" in modelo  # deixa claro que nao sao eventos reais


def test_cli_com_agenda_velha_marca_indisponivel(tmp_path, capsys):
    caminho = arquivo_de_eventos(tmp_path, [bruto()],
                                 atualizado_em=AGORA - timedelta(days=5))
    main(["--arquivo", caminho, "--instante", AGORA.isoformat(), "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert dados["agenda"]["disponibilidade"] == "desatualizada"
    assert dados["avaliacao"]["noticias_indisponiveis"] is True


def test_cli_recusa_instante_invalido():
    with pytest.raises(SystemExit):
        main(["--instante", "ontem"])
