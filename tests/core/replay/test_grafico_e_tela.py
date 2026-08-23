"""O grafico com marcadores e a tela do replay."""

from __future__ import annotations

import pytest

from cashinho.core.replay import (
    EventoReplay,
    FitaDeMercado,
    TipoEvento,
    grafico,
    pagina,
    painel_conta,
    painel_pipeline,
    painel_progresso,
    resumo,
    ultimos_eventos,
)
from cashinho.core.replay.grafico import ALTA, BAIXA, PAVIO
from cashinho.models import Direction

from .factories import pregao, replay, serie, serie_alta


def _fita(n: int = 40, avancos: int = 30) -> FitaDeMercado:
    f = FitaDeMercado(serie_alta(n=n))
    for _ in range(avancos):
        f.avancar()
    return f


# --- o grafico ------------------------------------------------------------------


def test_o_grafico_desenha_candles():
    texto = grafico(_fita(), altura=12, largura=30)

    assert ALTA in texto or BAIXA in texto
    assert PAVIO in texto
    assert "R$" in texto  # eixo de precos


def test_alta_e_baixa_tem_marcas_diferentes():
    fita = FitaDeMercado(serie([30.0, 30.5, 30.1, 30.6, 30.2]))
    for _ in range(5):
        fita.avancar()
    texto = grafico(fita, altura=10, largura=10)

    assert ALTA in texto
    assert BAIXA in texto


def test_o_grafico_so_desenha_o_que_ja_passou():
    fita = _fita(n=100, avancos=20)
    texto = grafico(fita, altura=10, largura=100)
    colunas = max(len(l.split("┤")[1]) for l in texto.splitlines() if "┤" in l)

    assert colunas <= 20


def test_o_grafico_marca_os_eventos():
    fita = _fita()
    candle = fita.candle(25)
    eventos = [
        EventoReplay(TipoEvento.SINAL, 25, candle.ts, candle.close, "sinal"),
        EventoReplay(TipoEvento.ENTRADA, 26, fita.candle(26).ts, fita.candle(26).close, "entrada",
                     Direction.LONG),
        EventoReplay(TipoEvento.STOP, 26, fita.candle(26).ts, fita.candle(26).low, "stop"),
        EventoReplay(TipoEvento.ALVO, 26, fita.candle(26).ts, fita.candle(26).high, "alvo"),
        EventoReplay(TipoEvento.SAIDA, 28, fita.candle(28).ts, fita.candle(28).close, "saida"),
    ]
    texto = grafico(fita, eventos, altura=14, largura=35)

    for marcador in ("s", "E", "S", "A", "X"):
        assert marcador in texto


def test_os_niveis_ganham_rotulo_a_direita():
    fita = _fita()
    candle = fita.candle(28)
    eventos = [EventoReplay(TipoEvento.ENTRADA, 28, candle.ts, candle.close, "entrada")]
    texto = grafico(fita, eventos, altura=14, largura=35)

    assert "E R$" in texto


def test_evento_fora_da_janela_nao_quebra():
    fita = _fita(n=200, avancos=150)
    candle = fita.candle(5)
    eventos = [EventoReplay(TipoEvento.ENTRADA, 5, candle.ts, candle.close, "antiga")]

    assert "┤" in grafico(fita, eventos, altura=10, largura=30)


def test_o_grafico_tem_legenda():
    texto = grafico(_fita())

    assert "sinal" in texto and "entrada" in texto and "stop" in texto


def test_poucos_candles_avisam_em_vez_de_quebrar():
    fita = FitaDeMercado(serie_alta(n=10))
    fita.avancar()

    assert "aguardando" in grafico(fita)


def test_cores_sao_opcionais_no_grafico():
    fita = _fita()
    assert "\033[" not in grafico(fita, cores=False)
    assert "\033[" in grafico(fita, cores=True)


# --- a tela ------------------------------------------------------------------------


def test_a_tela_traz_cabecalho_progresso_grafico_e_paineis():
    r, _ = pregao()
    r.executar(ate=120)
    texto = pagina(r)

    assert "MARKET REPLAY" in texto
    assert "PETR4" in texto
    assert "PIPELINE" in texto
    assert "CONTA" in texto
    assert "EVENTOS" in texto


def test_o_cabecalho_mostra_as_quatro_escolhas():
    r, _ = pregao()
    texto = pagina(r)

    assert "PETR4" in texto
    assert "1m" in texto
    assert "maxima" in texto
    assert "/2026" in texto  # a data do pregao


def test_o_progresso_avanca():
    r = replay(serie_alta(n=50))
    r.executar(ate=25)
    texto = painel_progresso(r)

    assert "25/50" in texto
    assert "50%" in texto


def test_o_painel_de_pipeline_conta_as_etapas():
    r, _ = pregao()
    r.executar()
    texto = painel_pipeline(r.estado)

    assert "sinais" in texto
    assert "barrados no auditor" in texto
    assert "entradas" in texto


def test_o_painel_de_conta_mostra_patrimonio_e_posicao():
    r, _ = pregao()
    r.executar(ate=200)
    texto = painel_conta(r)

    assert "patrimonio" in texto
    assert "posicao" in texto or "nenhuma posicao" in texto


def test_os_eventos_recentes_aparecem():
    r, _ = pregao()
    r.executar()
    texto = ultimos_eventos(r.estado.eventos)

    if r.estado.eventos:
        assert r.estado.eventos[-1].descricao[:20] in texto
    else:
        assert "nada ainda" in texto


def test_cores_sao_opcionais_na_tela():
    r, _ = pregao()
    r.executar(ate=100)

    assert "\033[" not in pagina(r, cores=False)
    assert "\033[" in pagina(r, cores=True)


def test_resumo_cabe_em_uma_linha():
    r, _ = pregao()
    r.executar(ate=100)
    linha = resumo(r)

    assert "\n" not in linha
    assert "candles" in linha
