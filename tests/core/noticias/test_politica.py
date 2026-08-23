"""A politica: descontar, reduzir posicao, bloquear - e nada alem disso."""

from __future__ import annotations

from datetime import timedelta

import pytest

from cashinho.core.noticias import (
    AvaliacaoDeEventos,
    AvaliadorDeEventos,
    ConfigEventos,
    Disponibilidade,
    FonteArquivo,
    FonteEmMemoria,
    JanelaDeProtecao,
    PoliticaDeEventos,
    Severidade,
    TipoDeEvento,
    ViesDirecional,
    agenda_indisponivel,
    risco_ajustado,
)
from cashinho.core.risk import RiskConfig
from cashinho.models import Direction

from .factories import AGORA, agenda, evento


def avaliar(eventos=(), symbol="PETR4", direcao=None, config=None,
            estado=Disponibilidade.DISPONIVEL, instante=AGORA):
    return PoliticaDeEventos(config).avaliar(
        agenda(eventos, disponibilidade=estado), symbol, instante, direcao)


# --- as invariantes da camada ------------------------------------------------


def test_avaliacao_nao_aceita_ajuste_positivo():
    """Uma notícia nao pode somar pontos a uma oportunidade."""
    with pytest.raises(ValueError, match="nao pode somar pontos"):
        AvaliacaoDeEventos(ajuste_de_score=5.0)


def test_avaliacao_nao_aceita_multiplicador_menor_que_um():
    with pytest.raises(ValueError, match="nao pode aumentar"):
        AvaliacaoDeEventos(multiplicador_de_risco=0.8)


def test_configuracao_com_multiplicador_abaixo_de_um_e_recusada():
    with pytest.raises(ValueError, match="so sabe reduzir"):
        ConfigEventos(multiplicadores={Severidade.ALTA: 0.5})


@pytest.mark.parametrize("tipo", list(TipoDeEvento))
@pytest.mark.parametrize("severidade", list(Severidade))
def test_nenhum_evento_produz_direcao_de_operacao(tipo, severidade):
    """A avaliacao nao tem campo de direcao para preencher."""
    a = avaliar([evento(tipo, severidade=severidade, vies=ViesDirecional.ALTA)])

    assert not hasattr(a, "direcao")
    assert not hasattr(a, "action")
    assert a.ajuste_de_score <= 0
    assert a.multiplicador_de_risco >= 1


def test_o_modulo_nao_conhece_compra_nem_venda():
    """Nenhum arquivo do modulo pode produzir BUY, SELL ou uma ordem."""
    import pathlib

    proibidos = ("Action.BUY", "Action.SELL", "Direction.LONG", "Direction.SHORT",
                 "place_order", "Signal(", "Opportunity(")
    for arquivo in pathlib.Path("src/cashinho/core/noticias").glob("*.py"):
        texto = arquivo.read_text()
        for termo in proibidos:
            assert termo not in texto, f"{arquivo.name} usa {termo}"


# --- bloqueio ----------------------------------------------------------------------


def test_juros_dentro_da_janela_bloqueia():
    a = avaliar([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=20,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is True
    assert "JUROS" in a.motivo


def test_juros_longe_da_janela_nao_bloqueia_mas_pesa():
    a = avaliar([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=180,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is False
    assert a.ajuste_de_score < 0


def test_o_bloqueio_vale_depois_do_evento_tambem():
    a = avaliar([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=-20,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is True


def test_resultados_de_outro_ativo_nao_bloqueiam_este():
    a = avaliar([evento(TipoDeEvento.RESULTADOS, symbol="VALE3", minutos=10)],
                symbol="PETR4")

    assert a.bloqueado is False
    assert a.ajuste_de_score == 0


def test_severidade_baixa_nao_bloqueia():
    a = avaliar([evento(TipoDeEvento.RESULTADOS, minutos=10, severidade=Severidade.BAIXA)])

    assert a.bloqueado is False
    assert a.ajuste_de_score < 0  # mas ainda desconta


def test_evento_nao_confirmado_avisa_mas_nao_bloqueia():
    """Data provavel nao para o robo."""
    a = avaliar([evento(TipoDeEvento.RESULTADOS, minutos=10,
                        severidade=Severidade.CRITICA, confirmado=False)])

    assert a.bloqueado is False
    assert a.avisos


def test_confianca_abaixo_do_minimo_so_registra():
    a = avaliar([evento(TipoDeEvento.RESULTADOS, minutos=10,
                        severidade=Severidade.CRITICA, confianca=0.2)])

    assert a.bloqueado is False
    assert a.ajuste_de_score == 0
    assert any("confianca" in x for x in a.avisos)


def test_evento_corporativo_nao_bloqueia_por_padrao():
    a = avaliar([evento(TipoDeEvento.EVENTO_CORPORATIVO, minutos=5,
                        severidade=Severidade.ALTA)])

    assert a.bloqueado is False
    assert a.ajuste_de_score < 0


def test_as_janelas_sao_configuraveis():
    cfg = ConfigEventos(janelas={TipoDeEvento.EVENTO_CORPORATIVO: JanelaDeProtecao(30, 30)})
    a = avaliar([evento(TipoDeEvento.EVENTO_CORPORATIVO, minutos=5)], config=cfg)

    assert a.bloqueado is True


# --- look-ahead ---------------------------------------------------------------------


def test_fato_relevante_futuro_e_ignorado():
    """Fato relevante nao e' agendado: usa-lo antes de sair e' ler o jornal de amanha."""
    a = avaliar([evento(TipoDeEvento.FATO_RELEVANTE, minutos=60,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is False
    assert a.ajuste_de_score == 0
    assert a.eventos  # ele aparece na lista, mas nao pesa


def test_fato_relevante_recem_ocorrido_bloqueia():
    a = avaliar([evento(TipoDeEvento.FATO_RELEVANTE, minutos=-30,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is True


def test_evento_agendavel_futuro_continua_valendo():
    """O contrario do fato relevante: Copom marcado e' conhecido com antecedencia."""
    a = avaliar([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=20,
                        severidade=Severidade.CRITICA)])

    assert a.bloqueado is True


# --- desconto de score e risco ---------------------------------------------------------


def test_severidade_maior_desconta_mais():
    critico = avaliar([evento(minutos=200, severidade=Severidade.CRITICA)])
    medio = avaliar([evento(minutos=200, severidade=Severidade.MEDIA)])

    assert critico.ajuste_de_score < medio.ajuste_de_score < 0


def test_vies_contrario_agrava_o_desconto():
    neutro = avaliar([evento(minutos=200, vies=ViesDirecional.INDEFINIDO)],
                     direcao=Direction.LONG)
    contra = avaliar([evento(minutos=200, vies=ViesDirecional.BAIXA)],
                     direcao=Direction.LONG)

    assert contra.ajuste_de_score < neutro.ajuste_de_score


def test_vies_a_favor_nao_diminui_o_desconto():
    """Notícia boa nao compensa notícia: este modulo so sabe apontar risco."""
    neutro = avaliar([evento(minutos=200, vies=ViesDirecional.INDEFINIDO)],
                     direcao=Direction.LONG)
    a_favor = avaliar([evento(minutos=200, vies=ViesDirecional.ALTA)],
                      direcao=Direction.LONG)

    assert a_favor.ajuste_de_score == neutro.ajuste_de_score


def test_o_desconto_tem_teto():
    muitos = [evento(minutos=200, severidade=Severidade.CRITICA) for _ in range(10)]
    a = avaliar(muitos, config=ConfigEventos(penalidade_maxima=40.0))

    assert a.ajuste_de_score == -40.0


def test_o_multiplicador_de_risco_e_o_do_pior_evento():
    a = avaliar([evento(minutos=200, severidade=Severidade.MEDIA),
                 evento(minutos=200, severidade=Severidade.CRITICA)])

    assert a.multiplicador_de_risco == 2.0


def test_risco_ajustado_reduz_a_posicao():
    a = avaliar([evento(minutos=200, severidade=Severidade.CRITICA)])
    config = RiskConfig(capital=100_000.0, risco_por_trade_pct=0.5)

    ajustado = risco_ajustado(config, a)

    assert ajustado.risco_por_trade_pct == pytest.approx(0.25)
    assert config.risco_por_trade_pct == 0.5  # o original nao muda


def test_sem_evento_o_risco_fica_igual():
    config = RiskConfig(capital=100_000.0, risco_por_trade_pct=0.5)

    assert risco_ajustado(config, avaliar([])) is config


def test_agenda_sem_evento_nao_pesa():
    a = avaliar([])

    assert a.pesou is False
    assert a.bloqueado is False
    assert a.ajuste_de_score == 0


# --- fonte indisponivel ------------------------------------------------------------------


def test_agenda_indisponivel_avisa_e_nao_bloqueia_por_padrao():
    a = PoliticaDeEventos().avaliar(
        agenda_indisponivel("a fonte caiu"), "PETR4", AGORA)

    assert a.noticias_indisponiveis is True
    assert a.bloqueado is False
    assert any("NOTICIAS INDISPONIVEIS" in x for x in a.avisos)


def test_da_para_exigir_agenda_para_operar():
    a = PoliticaDeEventos(ConfigEventos(sem_fonte_bloqueia=True)).avaliar(
        agenda_indisponivel("a fonte caiu"), "PETR4", AGORA)

    assert a.bloqueado is True
    assert "INDISPONIVEIS" in a.motivo


def test_agenda_desatualizada_nao_e_usada_para_decidir():
    a = avaliar([evento(TipoDeEvento.DECISAO_DE_JUROS, symbol="", minutos=10,
                        severidade=Severidade.CRITICA)],
                estado=Disponibilidade.DESATUALIZADA)

    assert a.bloqueado is False
    assert a.ajuste_de_score == 0
    assert a.noticias_indisponiveis is True


# --- o avaliador --------------------------------------------------------------------------


def test_o_avaliador_carrega_a_agenda_uma_vez():
    class FonteContada(FonteEmMemoria):
        vezes = 0

        def carregar(self, instante=None):
            FonteContada.vezes += 1
            return super().carregar(instante)

    av = AvaliadorDeEventos(FonteContada([evento()], AGORA))
    av.avaliar("PETR4", AGORA)
    av.avaliar("PETR4", AGORA)

    assert FonteContada.vezes == 1


def test_recarregar_forca_nova_leitura(tmp_path):
    from .factories import arquivo_de_eventos, bruto

    caminho = arquivo_de_eventos(tmp_path, [bruto()])
    av = AvaliadorDeEventos(FonteArquivo(caminho))

    assert len(av.agenda(AGORA)) == 1
    arquivo_de_eventos(tmp_path, [bruto(), bruto(symbol="VALE3")])
    assert len(av.agenda(AGORA)) == 1        # cache
    assert len(av.recarregar(AGORA)) == 2    # releitura
