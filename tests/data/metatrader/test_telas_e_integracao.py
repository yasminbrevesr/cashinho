"""As telas com feed em tempo real, e a integracao com o servico."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from cashinho.data.metatrader import MetaTraderMarketDataProvider
from cashinho.data.servico import (
    Finalidade,
    MarketDataService,
    TempoRealIndisponivelError,
)
from cashinho.data.status import StatusDados
from cashinho.data.view import secao_providers, secao_tempo_real
from cashinho.models import BRT

from .factories import AGORA, MT5Falso, provedor, tick_de_cotacao, tick_de_negocio


def servico(mt5=None):
    from .factories import terminal

    p = MetaTraderMarketDataProvider(terminal=terminal(mt5), relogio=lambda: AGORA)
    p.conectar()
    return MarketDataService(tempo_real=p, relogio=lambda: AGORA)


# --- a tela DADOS EM TEMPO REAL ---------------------------------------------


def test_a_tela_mostra_bid_ask_last_e_spread():
    texto = secao_tempo_real(provedor().cotacao("PETR4"))

    assert "DADOS EM TEMPO REAL" in texto
    assert "PETR4" in texto
    assert "42,06" in texto and "42,07" in texto     # bid e ask
    assert "Spread" in texto


def test_a_tela_mostra_os_dois_relogios():
    texto = secao_tempo_real(provedor().cotacao("PETR4"))

    assert "Cotacao em" in texto
    assert "Negocio em" in texto


def test_livro_zerado_aparece_como_ausencia_e_nao_como_zero():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    texto = secao_tempo_real(provedor(mt5).cotacao("PETR4"))

    assert "SEM LIVRO ATIVO" in texto
    assert "R$ 0,00" not in texto
    assert "0,00" not in texto.split("Last")[0]      # nao ha zero antes do Last


def test_o_ultimo_negocio_continua_visivel_sem_livro():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    texto = secao_tempo_real(provedor(mt5).cotacao("PETR4"))

    assert "42,07" in texto      # o last permanece


def test_dado_parado_leva_o_aviso():
    velho = AGORA - timedelta(minutes=30)
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(momento=velho)],
                   ticks_trade=[tick_de_negocio(momento=velho)])
    texto = secao_tempo_real(provedor(mt5).cotacao("PETR4"))

    assert "STALE" in texto


# --- System Health -----------------------------------------------------------


def test_o_painel_mostra_terminal_e_servidor():
    texto = secao_providers(servico())

    assert "MetaTrader" in texto or "metatrader" in texto
    assert "Terminal" in texto and "ONLINE" in texto
    assert "GenialInvestimentos-PRD" in texto


def test_o_painel_declara_trading_bloqueado():
    assert "BLOQUEADO" in secao_providers(servico())


def test_terminal_offline_aparece_como_tal():
    texto = secao_providers(servico(MT5Falso(conectado=False)))

    assert "TERMINAL OFFLINE" in texto


def test_o_painel_nao_expoe_dado_da_conta():
    texto = secao_providers(servico())

    assert "123456" not in texto     # login
    assert "98765" not in texto      # saldo


def test_com_metatrader_a_analise_em_tempo_real_fica_disponivel():
    assert "DISPONIVEL" in secao_providers(servico())


# --- integracao com o servico ---------------------------------------------------


def test_o_metatrader_atende_finalidade_de_tempo_real():
    leitura = servico().candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)

    assert leitura.fonte == "metatrader"
    assert leitura.utilizavel is True


def test_sem_terminal_nao_ha_queda_para_historico():
    """A proibicao central: dado historico nunca se passa por realtime."""
    from .factories import terminal

    p = MetaTraderMarketDataProvider(terminal=terminal(MT5Falso(conectado=False)),
                                     relogio=lambda: AGORA)
    p.conectar()
    from cashinho.data.fabrica import construir

    s = MarketDataService(historico=construir("demo"), tempo_real=p,
                          relogio=lambda: AGORA)

    from cashinho.data.base import DataError

    with pytest.raises(DataError, match="TERMINAL OFFLINE"):
        s.candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)

    # e o historico continua servindo o que e' historico
    assert s.candles("PETR4", "1d", 5, Finalidade.BACKTEST).utilizavel is True


def test_a_leitura_passa_pela_qualidade_de_dados():
    leitura = servico().candles("PETR4", "1m", 1, Finalidade.SCANNER_INTRADIARIO)

    assert leitura.qualidade.valida is True


def test_o_payload_do_servico_serializa():
    json.dumps(servico().para_dict())


# --- a CLI ------------------------------------------------------------------------


def test_a_cli_lista_o_metatrader(capsys):
    from cashinho.data.__main__ import main

    main(["--providers", "--sem-cor"])

    assert "metatrader" in capsys.readouterr().out


def test_o_acompanhamento_respeita_o_numero_de_vezes(capsys):
    from cashinho.data.__main__ import main

    esperas = []
    main(["--ativo", "PETR4", "--provider", "demo", "--timeframe", "1d",
          "--acompanhar", "3", "--vezes", "2", "--sem-cor"],
         dormir=lambda s: esperas.append(s))

    assert esperas == [3.0]          # duas leituras, uma espera entre elas


def test_o_acompanhamento_tem_intervalo_minimo(capsys):
    from cashinho.data.__main__ import main

    esperas = []
    main(["--ativo", "PETR4", "--provider", "demo", "--timeframe", "1d",
          "--acompanhar", "0.1", "--vezes", "2", "--sem-cor"],
         dormir=lambda s: esperas.append(s))

    assert esperas == [1.0]          # nao aceita alta frequencia
