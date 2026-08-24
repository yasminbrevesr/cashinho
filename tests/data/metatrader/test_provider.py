"""O provider MT5: quote, trade, bid/ask zero, candles e estado."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cashinho.data.base import DataError
from cashinho.data.metatrader import (
    MetaTraderMarketDataProvider,
    MT5Indisponivel,
    SimboloAmbiguoError,
    SimboloNaoEncontradoError,
)
from cashinho.data.status import StatusDados
from cashinho.models import BRT

from .factories import (
    AGORA,
    MT5Falso,
    candle,
    provedor,
    terminal,
    tick_de_cotacao,
    tick_de_negocio,
)


# --- ambiente sem MetaTrader --------------------------------------------


def test_sem_a_biblioteca_o_modulo_ainda_carrega():
    """Linux, CI e backtest nao podem quebrar por causa de um import."""
    from cashinho.data.metatrader.terminal import TerminalMT5

    t = TerminalMT5(mt5=None)
    t._mt5 = None
    # forca o caminho de import de verdade
    assert t.disponivel in (True, False)   # nao levanta


def test_biblioteca_ausente_vira_estado_descrito():
    from cashinho.data.metatrader.terminal import TerminalMT5

    class SemBiblioteca(TerminalMT5):
        @property
        def biblioteca(self):
            raise MT5Indisponivel("METATRADER NAO DISPONIVEL: nao instalada")

    info = SemBiblioteca().conectar()

    assert info.conectado is False
    assert "METATRADER NAO DISPONIVEL" in info.motivo


def test_initialize_que_falha_vira_terminal_offline():
    p = MetaTraderMarketDataProvider(
        terminal=terminal(MT5Falso(initialize_ok=False, erro=(-6, "Terminal: no IPC"))),
        relogio=lambda: AGORA)
    info = p.conectar()

    assert info.conectado is False
    assert "no IPC" in info.motivo


def test_terminal_desconectado_barra_a_leitura():
    p = provedor(MT5Falso(conectado=False))

    with pytest.raises(DataError, match="TERMINAL OFFLINE"):
        p.candles("PETR4", "1m", 1)


# --- a conta nunca aparece -------------------------------------------------


def test_o_payload_nao_expoe_dado_da_conta():
    """A account_info traz login e saldo; nada disso pode sair daqui."""
    import json

    p = provedor()
    texto = json.dumps(p.para_dict())

    assert "123456" not in texto       # login
    assert "98765" not in texto        # saldo
    assert "GenialInvestimentos-PRD" in texto   # servidor pode


# --- quote e trade sao fontes separadas -------------------------------------


def test_bid_e_ask_vem_dos_ticks_de_cotacao():
    p = provedor()
    evento = p.evento_de_cotacao("PETR4")

    assert (evento.bid, evento.ask) == (42.06, 42.07)
    assert evento.spread == pytest.approx(0.01)


def test_last_e_volume_vem_dos_ticks_de_negocio():
    p = provedor()
    evento = p.evento_de_negocio("PETR4")

    assert evento.last == 42.07
    assert evento.volume == 400


def test_a_cotacao_consolida_as_duas_fontes():
    cot = provedor().cotacao("PETR4")

    assert cot.bid == 42.06 and cot.ask == 42.07
    assert cot.last == 42.07 and cot.volume == 400
    assert cot.source == "metatrader"


def test_os_dois_relogios_ficam_separados():
    """Quote as 41.596 e trade as 41.601: juntar esconderia qual esta velho."""
    cot = provedor().cotacao("PETR4")

    assert cot.quote_timestamp is not None
    assert cot.trade_timestamp is not None
    assert cot.quote_timestamp != cot.trade_timestamp


def _nomes_chamados(caminho: str) -> set[str]:
    """Atributos realmente acessados no codigo - docstring nao conta.

    Procurar o termo no texto acusaria a propria documentacao que explica por
    que ele NAO e' usado. O que interessa e' a arvore sintatica.
    """
    import ast
    import pathlib

    arvore = ast.parse(pathlib.Path(caminho).read_text())
    return {no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)} | {
        no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)}


def test_o_provider_nao_usa_symbol_info_tick():
    """Ele ja voltou com bid=0 e ask=0 existindo book valido."""
    assert "symbol_info_tick" not in _nomes_chamados(
        "src/cashinho/data/metatrader/provider.py")


def test_o_terminal_tambem_nao_usa_symbol_info_tick():
    assert "symbol_info_tick" not in _nomes_chamados(
        "src/cashinho/data/metatrader/terminal.py")


# --- bid/ask zerados: ausencia de livro, nao preco -----------------------------


def test_bid_e_ask_zerados_viram_ausencia():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    cot = provedor(mt5).cotacao("PETR4")

    assert cot.bid is None and cot.ask is None
    assert cot.spread is None
    assert cot.tem_livro is False


def test_livro_zerado_nao_apaga_o_ultimo_negocio():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    cot = provedor(mt5).cotacao("PETR4")

    assert cot.last == 42.07     # o negocio continua disponivel, a parte
    assert cot.trade_timestamp is not None


def test_livro_zerado_vira_no_active_book():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    cot = provedor(mt5).cotacao("PETR4")

    assert cot.status is StatusDados.NO_ACTIVE_BOOK
    assert "SEM LIVRO ATIVO" in cot.aviso


def test_o_last_nunca_vira_bid():
    """Preencher o book com o ultimo negocio seria inventar cotacao."""
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
    cot = provedor(mt5).cotacao("PETR4")

    assert cot.bid is not cot.last
    assert cot.bid is None


def test_spread_so_existe_com_os_dois_lados():
    completo = provedor().cotacao("PETR4")
    sem_livro = provedor(MT5Falso(ticks_info=[tick_de_cotacao(bid=0.0, ask=0.0)])
                         ).cotacao("PETR4")

    assert completo.spread == pytest.approx(0.01)
    assert sem_livro.spread is None


def test_tick_com_um_lado_so_nao_forma_livro():
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(bid=42.06, ask=0.0)])

    assert provedor(mt5).cotacao("PETR4").tem_livro is False


# --- estado do feed --------------------------------------------------------------


def test_dado_fresco_no_pregao_e_online():
    assert provedor().cotacao("PETR4").status is StatusDados.ONLINE


def test_dado_parado_no_pregao_e_stale():
    velho = AGORA - timedelta(minutes=20)
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(momento=velho)],
                   ticks_trade=[tick_de_negocio(momento=velho)])

    assert provedor(mt5).cotacao("PETR4").status is StatusDados.STALE


def test_dado_parado_fora_do_pregao_e_mercado_fechado():
    """Nao e' defeito: as 20h o ultimo tick e' das 17h55 e esta certo."""
    noite = datetime(2026, 8, 20, 20, 30, tzinfo=BRT)
    velho = datetime(2026, 8, 20, 17, 50, tzinfo=BRT)
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(momento=velho)],
                   ticks_trade=[tick_de_negocio(momento=velho)])

    cot = provedor(mt5, agora=noite).cotacao("PETR4")

    assert cot.status is StatusDados.MARKET_CLOSED
    assert cot.status.mercado_parado is True


def test_sem_tick_nenhum_e_offline():
    assert provedor(MT5Falso(ticks_info=[], ticks_trade=[])).cotacao("PETR4").status \
        is StatusDados.OFFLINE


def test_o_limite_de_stale_e_configuravel():
    velho = AGORA - timedelta(seconds=90)
    mt5 = MT5Falso(ticks_info=[tick_de_cotacao(momento=velho)],
                   ticks_trade=[tick_de_negocio(momento=velho)])

    frouxo = provedor(mt5, mt5_stale_s=300).cotacao("PETR4")
    rigoroso = provedor(mt5, mt5_stale_s=30).cotacao("PETR4")

    assert frouxo.status is StatusDados.ONLINE
    assert rigoroso.status is StatusDados.STALE


# --- simbolos -----------------------------------------------------------------------


def test_petr4_resolve_exato_e_e_selecionado():
    mt5 = MT5Falso()
    p = provedor(mt5)
    p.resolver_simbolo("PETR4")

    assert "PETR4" in mt5.selecionados


def test_simbolo_ambiguo_nao_vira_escolha():
    with pytest.raises(SimboloAmbiguoError):
        provedor().resolver_simbolo("PETR")


def test_simbolo_inexistente_e_recusado():
    with pytest.raises(SimboloNaoEncontradoError):
        provedor().resolver_simbolo("XPTO9")


def test_a_resolucao_e_lembrada():
    mt5 = MT5Falso()
    p = provedor(mt5)
    p.resolver_simbolo("PETR4")
    p.resolver_simbolo("PETR4")

    assert mt5.selecionados.count("PETR4") == 1


# --- candles -------------------------------------------------------------------------


def test_traz_candles_reais():
    serie = provedor().candles("PETR4", "1m", 1)

    assert len(serie) >= 1
    assert serie.symbol == "PETR4" and serie.timeframe == "1m"


def test_o_volume_real_e_preferido():
    serie = provedor().candles("PETR4", "1m", 1)

    assert serie.candles[-1].volume == 340_000


def test_os_seis_timeframes_estao_mapeados():
    from cashinho.data.metatrader import TIMEFRAMES

    assert set(TIMEFRAMES) == {"1m", "5m", "15m", "30m", "60m", "1d"}


def test_timeframe_fora_do_mapa_e_recusado():
    with pytest.raises(DataError, match="nao mapeado"):
        provedor().candles("PETR4", "2m", 1)


def test_todos_os_timeframes_do_mapa_funcionam():
    from cashinho.data.metatrader import TIMEFRAMES

    p = provedor(MT5Falso(candles=[candle(m * 1440) for m in range(5, 0, -1)]))
    for tf in TIMEFRAMES:
        assert len(p.candles("PETR4", tf, 5)) >= 1


# --- o candle em formacao ---------------------------------------------------------------


def test_o_candle_em_formacao_fica_de_fora():
    """A posicao 0 do MT5 e' o candle que ainda esta abrindo."""
    em_formacao = candle(0)          # abriu neste minuto: ainda nao fechou
    fechados = [candle(m) for m in (3, 2, 1)]
    p = provedor(MT5Falso(candles=fechados + [em_formacao]))

    serie = p.candles("PETR4", "1m", 1)

    assert len(serie) == 3
    assert all(c.ts + timedelta(minutes=1) <= AGORA for c in serie.candles)


def test_nao_corta_o_ultimo_as_cegas():
    """[:-1] jogaria fora um candle FECHADO logo apos a virada do periodo."""
    fechados = [candle(m) for m in (3, 2, 1)]   # nenhum em formacao
    p = provedor(MT5Falso(candles=fechados))

    assert len(p.candles("PETR4", "1m", 1)) == 3


def test_so_candles_em_formacao_e_erro_e_nao_serie_vazia():
    p = provedor(MT5Falso(candles=[candle(0)]))

    with pytest.raises(DataError, match="em formacao"):
        p.candles("PETR4", "1m", 1)


def test_o_corte_respeita_a_duracao_do_timeframe():
    """Um candle de 5m aberto ha 3 minutos ainda esta em formacao."""
    p = provedor(MT5Falso(candles=[candle(3), candle(8)]))

    serie = p.candles("PETR4", "5m", 1)

    assert len(serie) == 1      # so o de 8 minutos atras fechou


# --- capacidades ---------------------------------------------------------------------------


def test_trading_e_falso_e_declarado():
    assert provedor().capacidades.trading is False


def test_as_capacidades_de_tempo_real_sao_declaradas():
    c = provedor().capacidades

    assert c.cotacao_em_tempo_real is True
    assert c.ticks_em_tempo_real is True
    assert c.intradiario_1m is True
    assert c.candles_historicos is True
    assert c.serve_para_day_trade is True


def test_livro_de_ofertas_e_detectado_nao_presumido():
    sem = provedor(MT5Falso(tem_livro=False))
    com = provedor(MT5Falso(tem_livro=True))

    assert sem.capacidades.livro_de_ofertas is False
    assert sem.livro_disponivel("PETR4") is False
    assert com.livro_disponivel("PETR4") is True
    assert com.capacidades_de("PETR4").livro_de_ofertas is True


def test_livro_indisponivel_nao_quebra_cotacao_nem_candles():
    p = provedor(MT5Falso(tem_livro=False))

    assert p.cotacao("PETR4").last == 42.07
    assert len(p.candles("PETR4", "1m", 1)) >= 1


# --- a proibicao absoluta: nada de ordem -------------------------------------------------------


def test_o_provider_nao_tem_metodo_de_ordem():
    proibidos = ("order_send", "buy", "sell", "place_order", "cancel_order",
                 "modify_order", "close_position")
    metodos = dir(MetaTraderMarketDataProvider)

    assert [m for m in proibidos if m in metodos] == []


# Funcoes que MODIFICAM posicao ou enviam ordem. Leitura nao entra aqui:
# positions_get, positions_total e account_info sao consulta, e proibi-las
# confundiria "nao operar" com "nao enxergar".
ENVIAM_ORDEM = {
    "order_send",       # envia ordem de verdade
    "order_check",      # etapa do fluxo de envio
    "place_order",
    "buy", "sell",
    "cancel_order", "modify_order", "close_position",
}


def test_nenhum_arquivo_do_adapter_chama_funcao_de_ordem():
    """O que vale e' o codigo: a docstring cita os nomes para dizer que nao usa."""
    import pathlib

    culpados = []
    for arquivo in pathlib.Path("src/cashinho/data/metatrader").glob("*.py"):
        usados = _nomes_chamados(str(arquivo)) & ENVIAM_ORDEM
        if usados:
            culpados.append(f"{arquivo.name}: {', '.join(sorted(usados))}")

    assert culpados == []


def test_leitura_de_posicao_nao_e_operacao_proibida():
    """positions_get e' consulta: proibi-la confundiria 'nao operar' com
    'nao enxergar'. Ela nao e' usada hoje, mas nao esta vetada."""
    assert "positions_get" not in ENVIAM_ORDEM
    assert "positions_total" not in ENVIAM_ORDEM
    assert "account_info" not in ENVIAM_ORDEM


def test_so_o_terminal_importa_a_biblioteca():
    """O dominio nunca ve MetaTrader5."""
    import pathlib
    import re

    raiz = pathlib.Path("src/cashinho")
    culpados = []
    for arquivo in raiz.rglob("*.py"):
        if arquivo.name == "terminal.py" and "metatrader" in str(arquivo):
            continue
        if re.search(r"^\s*import MetaTrader5|from MetaTrader5", arquivo.read_text(), re.M):
            culpados.append(str(arquivo))

    assert culpados == []
