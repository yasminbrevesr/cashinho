"""A tela Analise: sinal, justificativas e os fatores dos dois lados."""

from __future__ import annotations

from cashinho.core.strategy import (
    AVISO_CURTO,
    Action,
    BaselineConfig,
    BaselineTendenciaVolumeATR,
    StrategyContext,
    faixa_de_aviso,
    linha_de_lista,
    tela_analise,
)

from .factories import serie_alta, serie_embaralhada

COMPRA = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_alta()))
ESPERA = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_alta(volume_final=1.0)))
NADA = BaselineTendenciaVolumeATR().avaliar(StrategyContext("PETR4", serie_embaralhada()))


def test_tela_mostra_o_sinal():
    texto = tela_analise(COMPRA)

    assert "ANALISE · PETR4 · 5m" in texto
    assert " SINAL" in texto
    assert "BUY" in texto
    assert "confianca" in texto


def test_tela_mostra_as_justificativas():
    texto = tela_analise(COMPRA)

    assert "JUSTIFICATIVAS" in texto
    for razao in COMPRA.reasons:
        assert razao in texto


def test_tela_separa_fatores_favoraveis_e_contrarios():
    texto = tela_analise(COMPRA)

    assert "FATORES FAVORAVEIS" in texto
    assert "FATORES CONTRARIOS" in texto
    for f in COMPRA.favoraveis:
        assert f.nome in texto
    for f in COMPRA.contrarios:
        assert f.nome in texto


def test_fatores_trazem_o_numero_que_os_justifica():
    texto = tela_analise(COMPRA)
    fator_volume = next(f for f in COMPRA.factors if f.nome == "volume")

    assert fator_volume.detalhe in texto
    assert "x a media" in texto


def test_tela_avisa_que_a_estrategia_e_so_de_validacao():
    for sinal in (COMPRA, ESPERA, NADA):
        texto = tela_analise(sinal)
        assert AVISO_CURTO in texto
        assert "NAO E' RECOMENDACAO" in texto


def test_aviso_aparece_antes_do_sinal():
    texto = tela_analise(COMPRA)

    assert texto.index(AVISO_CURTO) < texto.index(" SINAL")


def test_tela_de_wait_mostra_o_que_falta():
    texto = tela_analise(ESPERA)

    assert "WAIT" in texto
    assert "acompanhar" in texto
    assert "volume" in texto


def test_tela_de_none_mostra_o_que_derrubou_a_leitura():
    """O ATR passou; o empilhamento nao. A tela precisa deixar isso explicito."""
    texto = tela_analise(NADA)
    contrarios = texto.split("FATORES CONTRARIOS")[1]

    assert "NONE" in texto
    assert "nada a fazer" in texto
    assert "empilhamento das medias" in contrarios
    assert "medias fora de ordem" in contrarios


def test_niveis_aparecem_marcados_como_referencia():
    texto = tela_analise(COMPRA)

    assert "NIVEIS DE REFERENCIA" in texto
    assert "nao sao ordens" in texto
    assert "entrada" in texto and "stop" in texto and "alvo" in texto


def test_invalidacao_aparece_na_tela():
    texto = tela_analise(COMPRA)

    assert "INVALIDACAO" in texto
    assert COMPRA.invalidation in texto


def test_cores_sao_opcionais():
    assert "\033[" not in tela_analise(COMPRA, cores=False)
    assert "\033[" in tela_analise(COMPRA, cores=True)


def test_faixa_de_aviso_some_para_estrategia_nao_experimental():
    import dataclasses

    definitiva = dataclasses.replace(COMPRA, experimental=False)
    assert faixa_de_aviso(definitiva) == ""
    assert AVISO_CURTO not in tela_analise(definitiva)


def test_linha_de_lista_cabe_em_uma_linha():
    linha = linha_de_lista(ESPERA)

    assert "\n" not in linha
    assert "PETR4" in linha and "WAIT" in linha
    assert "falta: volume" in linha
