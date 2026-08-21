"""O ponto inegociavel: nenhuma estrategia sobrescreve uma rejeicao."""

from __future__ import annotations

import dataclasses

import pytest

from cashinho.core.risk import (
    PedidoOperacao,
    RiskDecision,
    RiskManager,
    RiskRejectionError,
)
from cashinho.models import Direction

from .factories import compra, config, gerente


def _rejeitada(rm: RiskManager) -> RiskDecision:
    rm.acionar_kill_switch("bloqueio de teste")
    return rm.avaliar(compra())


def _rejeitada_sem_travar_o_gerente(rm: RiskManager) -> RiskDecision:
    """Rejeicao por ordem invalida: o gerente segue liberado para os demais."""
    return rm.avaliar(PedidoOperacao("PETR4", Direction.LONG, 10.0, 10.0))


# --- a decisao e' imutavel -------------------------------------------------------


def test_nao_da_para_virar_uma_rejeicao_em_aprovacao():
    d = _rejeitada(gerente())

    with pytest.raises(dataclasses.FrozenInstanceError):
        d.allowed = True


def test_nao_da_para_inflar_a_quantidade_da_decisao():
    rm = gerente()
    d = rm.avaliar(compra())

    for campo, valor in (("position_size", 999_999), ("monetary_risk", 1e9), ("reason", "vai que da")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(d, campo, valor)


def test_rejeicao_sempre_zera_o_tamanho():
    d = _rejeitada(gerente())

    assert d.allowed is False
    assert d.position_size == 0
    assert d.monetary_risk == 0.0
    assert d.rejeitada is True


# --- so o gerente autoriza ---------------------------------------------------------


def test_abrir_com_decisao_rejeitada_levanta():
    rm = gerente()
    d = _rejeitada(rm)

    with pytest.raises(RiskRejectionError, match="rejeitada pelo risco"):
        rm.abrir(d)


def test_decisao_forjada_por_fora_nao_abre_posicao():
    """Construir um RiskDecision(allowed=True) na mao nao engana o gerente."""
    rm = gerente()
    forjada = RiskDecision(
        allowed=True,
        reason="a estrategia acha que pode",
        position_size=10_000,
        monetary_risk=1.0,
        portfolio_exposure=0.0,
        symbol="PETR4",
        direcao=Direction.LONG,
        entrada=10.0,
        stop=9.0,
        id="id-inventado",
    )

    with pytest.raises(RiskRejectionError, match="nao reconhecida"):
        rm.abrir(forjada)
    assert rm.estado.posicoes == {}


def test_decisao_copiada_com_allowed_true_tambem_e_recusada():
    """dataclasses.replace burla o frozen, mas nao o registro do gerente."""
    rm = gerente()
    d = _rejeitada_sem_travar_o_gerente(rm)
    clonada = dataclasses.replace(d, allowed=True, position_size=500)

    with pytest.raises(RiskRejectionError, match="nao reconhecida"):
        rm.abrir(clonada)


def test_decisao_de_outro_gerente_nao_vale():
    rm_a, rm_b = gerente(), gerente()
    d = rm_a.avaliar(compra())

    with pytest.raises(RiskRejectionError, match="nao reconhecida"):
        rm_b.abrir(d)


def test_decisao_nao_pode_ser_usada_duas_vezes():
    rm = gerente(config(permitir_piramide=True))
    d = rm.avaliar(compra())
    rm.abrir(d)
    rm.fechar("PETR4", 10.5)

    with pytest.raises(RiskRejectionError, match="nao reconhecida"):
        rm.abrir(d)


def test_bloqueio_surgido_entre_a_analise_e_a_execucao_impede_a_ordem():
    rm = gerente()
    d = rm.avaliar(compra())
    rm.acionar_kill_switch("parou tudo agora")

    with pytest.raises(RiskRejectionError, match="mudou entre a analise e a execucao"):
        rm.abrir(d)


def test_mudar_os_limites_invalida_decisoes_ja_emitidas():
    rm = gerente()
    d = rm.avaliar(compra())
    rm.atualizar_config(risco_por_trade_pct=0.1)

    with pytest.raises(RiskRejectionError, match="nao reconhecida"):
        rm.abrir(d)


# --- o risco nao conhece estrategia ---------------------------------------------------


def test_o_pedido_nao_tem_campo_de_estrategia():
    """Se desse para mandar 'score' ou 'confianca', daria para negociar com o risco."""
    campos = {f.name for f in dataclasses.fields(PedidoOperacao)}

    assert campos == {"symbol", "direcao", "entrada", "stop", "alvo", "preco_atual", "referencia"}
    assert "score" not in campos and "confianca" not in campos and "setup" not in campos


def test_a_mesma_ordem_recebe_a_mesma_decisao_venha_de_onde_vier():
    rm = gerente()
    de_uma_estrategia = rm.avaliar(
        PedidoOperacao("PETR4", Direction.LONG, 10.0, 9.5, referencia="rompimento-vwap")
    )
    de_outra = rm.avaliar(
        PedidoOperacao("PETR4", Direction.LONG, 10.0, 9.5, referencia="pullback-fibo")
    )

    assert de_uma_estrategia.position_size == de_outra.position_size
    assert de_uma_estrategia.monetary_risk == de_outra.monetary_risk
    assert de_uma_estrategia.allowed == de_outra.allowed


def test_o_gerente_nao_expoe_nenhum_atalho_de_aprovacao():
    metodos = {m for m in dir(RiskManager) if not m.startswith("_")}
    proibidos = {"forcar", "aprovar", "permitir", "override", "ignorar_limites", "liberar_ordem"}

    assert not (metodos & proibidos)
