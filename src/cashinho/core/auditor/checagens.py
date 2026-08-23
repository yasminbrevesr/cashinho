"""As onze frentes de invalidacao.

Cada checagem recebe o contexto e tenta derrubar a oportunidade por um motivo
especifico. Todas devolvem uma :class:`Checagem` - inclusive quando nao
conseguem invalidar, porque "procurei resistencia no caminho e ha 3,2 ATR de
espaco livre" e' uma informacao tao util quanto o contrario.

Quando falta dado para checar, a checagem sai com ``verificada=False``: nao
vira fator favoravel nem contrario. Ausencia de evidencia nao e' evidencia de
ausencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ...indicators.core import ema
from ...indicators.momentum import rsi as calcula_rsi
from ...indicators.volume import volume_relativo
from ...models import Direction, Series, formata_dinheiro
from ..confluencia.estados import Vies
from ..structure.models import MarketStructure, TipoEvento
from ..oportunidade.modelos import Opportunity
from .modelos import Checagem, Severidade


@dataclass(frozen=True)
class ConfigAuditor:
    """Os limiares do auditor. Mais duros que os do score, de proposito."""

    # zonas
    zona_critica_atr: float = 0.7  # parede colada na entrada
    zona_alerta_atr: float = 1.5
    # volume
    volume_critico: float = 0.7  # movimento sem participacao nenhuma
    volume_alerta: float = 1.0
    # entrada atrasada
    distancia_critica_atr: float = 3.5  # preco esticado em relacao a media
    distancia_alerta_atr: float = 2.0
    # risco/retorno
    rr_critico: float = 1.2
    rr_alerta: float = 1.8
    # volatilidade
    atr_critico_pct: float = 3.0
    atr_alerta_pct: float = 2.0
    # stop
    stop_critico_atr: float = 3.5
    stop_alerta_atr: float = 2.5
    stop_critico_pct: float = 3.0  # % do preco
    # descontos no score
    desconto_critico: float = 25.0
    desconto_alerta: float = 6.0
    desconto_observacao: float = 0.0


@dataclass
class ContextoAuditoria:
    """Tudo o que as checagens precisam - montado uma vez pelo auditor."""

    op: Opportunity
    agora: datetime
    cfg: ConfigAuditor = field(default_factory=ConfigAuditor)
    estrutura: Optional[MarketStructure] = None
    serie_setup: Optional[Series] = None
    serie_trigger: Optional[Series] = None

    @property
    def alta(self) -> bool:
        return self.op.direction is Direction.LONG

    @property
    def atr(self) -> float:
        if self.estrutura is not None and self.estrutura.atr:
            return self.estrutura.atr
        return max(abs(self.op.entry) * 0.005, 1e-9)

    @property
    def tem_mercado(self) -> bool:
        return self.estrutura is not None and self.serie_setup is not None


def _ok(chave: str, titulo: str, detalhe: str, **evidencia) -> Checagem:
    return Checagem(chave, titulo, True, detalhe, evidencia=evidencia)


def _falha(chave: str, titulo: str, detalhe: str, severidade: Severidade,
           cfg: ConfigAuditor, **evidencia) -> Checagem:
    desconto = {
        Severidade.CRITICO: cfg.desconto_critico,
        Severidade.ALERTA: cfg.desconto_alerta,
        Severidade.OBSERVACAO: cfg.desconto_observacao,
    }[severidade]
    return Checagem(chave, titulo, False, detalhe, severidade, -desconto, evidencia=evidencia)


def _sem_dados(chave: str, titulo: str, motivo: str) -> Checagem:
    return Checagem(chave, titulo, False, motivo, verificada=False)


# ---------------------------------------------------------------------------
# 1 e 2 - zonas no caminho
# ---------------------------------------------------------------------------


def resistencia_proxima(ctx: ContextoAuditoria) -> Checagem:
    """Numa compra, resistencia colada e' teto. Numa venda, e' o apoio do stop."""
    titulo = "resistencia proxima"
    if not ctx.tem_mercado:
        return _sem_dados("resistencia_proxima", titulo, "sem estrutura para checar")

    zona = ctx.estrutura.resistencia
    if zona is None:
        return _ok("resistencia_proxima", titulo, "nenhuma resistencia mapeada acima do preco")

    distancia = zona.distancia(ctx.op.entry) / ctx.atr
    onde = formata_dinheiro(zona.mid)
    if not ctx.alta:
        return _ok("resistencia_proxima", titulo,
                   f"resistencia em {onde} fica a favor da venda ({distancia:.1f} ATR acima)")

    if distancia <= ctx.cfg.zona_critica_atr:
        return _falha("resistencia_proxima", titulo,
                      f"resistencia em {onde} a apenas {distancia:.1f} ATR da entrada "
                      f"({zona.toques} toque(s), forca {zona.forca:.2f})",
                      Severidade.CRITICO, ctx.cfg, distancia_atr=distancia)
    if distancia <= ctx.cfg.zona_alerta_atr:
        return _falha("resistencia_proxima", titulo,
                      f"resistencia em {onde} a {distancia:.1f} ATR - pouco espaco para o alvo",
                      Severidade.ALERTA, ctx.cfg, distancia_atr=distancia)
    return _ok("resistencia_proxima", titulo,
               f"{distancia:.1f} ATR de espaco livre ate a resistencia de {onde}")


def suporte_proximo(ctx: ContextoAuditoria) -> Checagem:
    """Numa venda, suporte colado e' chao. Numa compra, e' apoio."""
    titulo = "suporte proximo"
    if not ctx.tem_mercado:
        return _sem_dados("suporte_proximo", titulo, "sem estrutura para checar")

    zona = ctx.estrutura.suporte
    if zona is None:
        return _ok("suporte_proximo", titulo, "nenhum suporte mapeado abaixo do preco")

    distancia = zona.distancia(ctx.op.entry) / ctx.atr
    onde = formata_dinheiro(zona.mid)
    if ctx.alta:
        return _ok("suporte_proximo", titulo,
                   f"suporte em {onde} a {distancia:.1f} ATR abaixo serve de apoio a compra")

    if distancia <= ctx.cfg.zona_critica_atr:
        return _falha("suporte_proximo", titulo,
                      f"suporte em {onde} a apenas {distancia:.1f} ATR da entrada "
                      f"({zona.toques} toque(s))",
                      Severidade.CRITICO, ctx.cfg, distancia_atr=distancia)
    if distancia <= ctx.cfg.zona_alerta_atr:
        return _falha("suporte_proximo", titulo,
                      f"suporte em {onde} a {distancia:.1f} ATR - pouco espaco para a queda",
                      Severidade.ALERTA, ctx.cfg, distancia_atr=distancia)
    return _ok("suporte_proximo", titulo,
               f"{distancia:.1f} ATR de espaco livre ate o suporte de {onde}")


# ---------------------------------------------------------------------------
# 3 - volume
# ---------------------------------------------------------------------------


def baixo_volume(ctx: ContextoAuditoria) -> Checagem:
    titulo = "baixo volume"
    if ctx.serie_trigger is None or len(ctx.serie_trigger) < 5:
        return _sem_dados("baixo_volume", titulo, "sem serie de gatilho para medir volume")

    vrel = volume_relativo(ctx.serie_trigger.volumes, 20)[-1]
    if vrel is None:
        return _sem_dados("baixo_volume", titulo, "media de volume ainda sem valor")

    if vrel < ctx.cfg.volume_critico:
        return _falha("baixo_volume", titulo,
                      f"movimento com {vrel:.2f}x a media de volume - praticamente sem participacao",
                      Severidade.CRITICO, ctx.cfg, volume_relativo=vrel)
    if vrel < ctx.cfg.volume_alerta:
        return _falha("baixo_volume", titulo,
                      f"volume de {vrel:.2f}x a media, abaixo do normal",
                      Severidade.ALERTA, ctx.cfg, volume_relativo=vrel)
    return _ok("baixo_volume", titulo, f"volume de {vrel:.2f}x a media sustenta o movimento")


# ---------------------------------------------------------------------------
# 4 - divergencias
# ---------------------------------------------------------------------------


def divergencias(ctx: ContextoAuditoria) -> Checagem:
    """Preco fez topo mais alto e o RSI nao acompanhou (ou o espelho na baixa)."""
    titulo = "divergencia de momentum"
    if not ctx.tem_mercado:
        return _sem_dados("divergencias", titulo, "sem estrutura para comparar com o momentum")

    e = ctx.estrutura
    extremos = e.swing_highs if ctx.alta else e.swing_lows
    if len(extremos) < 2:
        return _sem_dados("divergencias", titulo, "menos de dois swings para comparar")

    valores = calcula_rsi(ctx.serie_setup.closes, 14)
    a, b = extremos[-2], extremos[-1]
    if a.indice >= len(valores) or b.indice >= len(valores):
        return _sem_dados("divergencias", titulo, "RSI sem valor nos swings")
    rsi_a, rsi_b = valores[a.indice], valores[b.indice]
    if rsi_a is None or rsi_b is None:
        return _sem_dados("divergencias", titulo, "RSI sem valor nos swings")

    if ctx.alta:
        preco_subiu = b.preco > a.preco
        rsi_caiu = rsi_b < rsi_a - 2
        divergiu = preco_subiu and rsi_caiu
        texto = (f"topo em {formata_dinheiro(b.preco)} acima do anterior, mas o RSI caiu de "
                 f"{rsi_a:.0f} para {rsi_b:.0f}")
    else:
        preco_caiu = b.preco < a.preco
        rsi_subiu = rsi_b > rsi_a + 2
        divergiu = preco_caiu and rsi_subiu
        texto = (f"fundo em {formata_dinheiro(b.preco)} abaixo do anterior, mas o RSI subiu de "
                 f"{rsi_a:.0f} para {rsi_b:.0f}")

    if divergiu:
        return _falha("divergencias", titulo, texto + " - momentum nao acompanha o preco",
                      Severidade.ALERTA, ctx.cfg, rsi_anterior=rsi_a, rsi_atual=rsi_b)
    return _ok("divergencias", titulo,
               f"RSI acompanha o preco entre os dois ultimos swings ({rsi_a:.0f} -> {rsi_b:.0f})")


# ---------------------------------------------------------------------------
# 5 - entrada atrasada
# ---------------------------------------------------------------------------


def entrada_atrasada(ctx: ContextoAuditoria) -> Checagem:
    """O movimento ja andou: entrar aqui e' pagar o preco de quem chegou antes."""
    titulo = "entrada atrasada"
    if not ctx.tem_mercado or len(ctx.serie_setup) < 25:
        return _sem_dados("entrada_atrasada", titulo, "serie curta demais para medir o esticamento")

    media = ema(ctx.serie_setup.closes, 21)[-1]
    if media is None:
        return _sem_dados("entrada_atrasada", titulo, "media de 21 ainda sem valor")

    distancia = abs(ctx.op.entry - media) / ctx.atr
    do_lado_certo = (ctx.op.entry > media) if ctx.alta else (ctx.op.entry < media)

    # o que importa e' a distancia: colado na media nao ha atraso nenhum,
    # esteja o preco um centavo acima ou abaixo dela
    if distancia < ctx.cfg.distancia_alerta_atr:
        return _ok("entrada_atrasada", titulo,
                   f"entrada a {distancia:.1f} ATR da EMA21, sem esticamento")
    if not do_lado_certo:
        return _ok("entrada_atrasada", titulo,
                   f"preco {distancia:.1f} ATR do outro lado da EMA21 - "
                   f"a favor da entrada, nao contra")

    if distancia >= ctx.cfg.distancia_critica_atr:
        return _falha("entrada_atrasada", titulo,
                      f"preco a {distancia:.1f} ATR da EMA21 - o movimento ja andou, "
                      f"a entrada aqui compra o topo do impulso",
                      Severidade.CRITICO, ctx.cfg, distancia_atr=distancia)
    return _falha("entrada_atrasada", titulo,
                  f"preco a {distancia:.1f} ATR da EMA21 - entrada ja um pouco esticada",
                  Severidade.ALERTA, ctx.cfg, distancia_atr=distancia)


# ---------------------------------------------------------------------------
# 6 - risco/retorno
# ---------------------------------------------------------------------------


def risco_retorno_ruim(ctx: ContextoAuditoria) -> Checagem:
    titulo = "risco/retorno ruim"
    rr = ctx.op.risk_reward
    if ctx.op.entry <= 0:
        # nao ha operacao definida para auditar - inventar uma critica aqui
        # so poluiria o veredito de uma oportunidade que nem existe
        return _sem_dados("risco_retorno_ruim", titulo, "oportunidade sem niveis definidos")
    if rr <= 0:
        return _falha("risco_retorno_ruim", titulo, "sem risco/retorno calculavel",
                      Severidade.CRITICO, ctx.cfg, rr=rr)
    if rr < ctx.cfg.rr_critico:
        return _falha("risco_retorno_ruim", titulo,
                      f"risco/retorno de {rr:.2f}: o alvo nao paga o risco",
                      Severidade.CRITICO, ctx.cfg, rr=rr)
    if rr < ctx.cfg.rr_alerta:
        return _falha("risco_retorno_ruim", titulo,
                      f"risco/retorno de {rr:.2f}, abaixo do confortavel "
                      f"({ctx.cfg.rr_alerta:.1f})",
                      Severidade.ALERTA, ctx.cfg, rr=rr)
    return _ok("risco_retorno_ruim", titulo, f"risco/retorno de {rr:.2f} paga o risco")


# ---------------------------------------------------------------------------
# 7 - volatilidade
# ---------------------------------------------------------------------------


def volatilidade_excessiva(ctx: ContextoAuditoria) -> Checagem:
    titulo = "volatilidade excessiva"
    if ctx.op.entry <= 0:
        return _sem_dados("volatilidade_excessiva", titulo, "sem preco de entrada")

    atr_pct = ctx.atr / ctx.op.entry * 100.0
    if atr_pct >= ctx.cfg.atr_critico_pct:
        return _falha("volatilidade_excessiva", titulo,
                      f"ATR de {atr_pct:.2f}% do preco - o ruido engole o setup",
                      Severidade.CRITICO, ctx.cfg, atr_pct=atr_pct)
    if atr_pct >= ctx.cfg.atr_alerta_pct:
        return _falha("volatilidade_excessiva", titulo,
                      f"ATR de {atr_pct:.2f}% do preco, acima do confortavel",
                      Severidade.ALERTA, ctx.cfg, atr_pct=atr_pct)
    return _ok("volatilidade_excessiva", titulo, f"ATR de {atr_pct:.2f}% do preco, dentro do operavel")


# ---------------------------------------------------------------------------
# 8 - falso rompimento
# ---------------------------------------------------------------------------


def falso_rompimento(ctx: ContextoAuditoria) -> Checagem:
    """Comprar logo depois de um rompimento de alta que falhou e' entrar na armadilha."""
    titulo = "falso rompimento"
    if not ctx.tem_mercado:
        return _sem_dados("falso_rompimento", titulo, "sem estrutura para checar rompimentos")

    evento = ctx.estrutura.falso_rompimento
    if evento is None:
        return _ok("falso_rompimento", titulo, "nenhum falso rompimento recente na estrutura")

    # o evento aponta para a REVERSAO; operar no sentido contrario a ela e'
    # operar justamente o movimento que acabou de falhar
    contra_a_reversao = evento.direcao is not ctx.op.direction
    if contra_a_reversao:
        return _falha("falso_rompimento", titulo,
                      f"a estrutura registrou {evento.descricao} - esta operacao vai no sentido "
                      f"do rompimento que falhou",
                      Severidade.CRITICO, ctx.cfg, forca=evento.forca)
    return _ok("falso_rompimento", titulo,
               f"o falso rompimento recente aponta para o mesmo lado da operacao "
               f"(forca {evento.forca:.2f})")


# ---------------------------------------------------------------------------
# 9 - timeframes conflitantes
# ---------------------------------------------------------------------------


def timeframes_conflitantes(ctx: ContextoAuditoria) -> Checagem:
    titulo = "timeframes conflitantes"
    leitura = ctx.op.leitura
    if leitura is None or not leitura.camadas:
        return _sem_dados("timeframes_conflitantes", titulo, "sem leitura multi-timeframe")

    alvo = Vies.de_direcao(ctx.op.direction)
    contra = [c for c in leitura.camadas if c.vies is not Vies.NEUTRAL and c.vies is not alvo]
    neutras = [c for c in leitura.camadas if c.vies is Vies.NEUTRAL]

    if contra:
        nomes = ", ".join(f"{c.timeframe} {c.valor}" for c in contra)
        severidade = Severidade.CRITICO if len(contra) > 1 else Severidade.ALERTA
        return _falha("timeframes_conflitantes", titulo,
                      f"camada(s) apontando para o outro lado: {nomes}",
                      severidade, ctx.cfg, contra=len(contra))
    if len(neutras) >= 2:
        nomes = ", ".join(f"{c.timeframe} {c.valor}" for c in neutras)
        return _falha("timeframes_conflitantes", titulo,
                      f"{len(neutras)} camadas sem direcao ({nomes}) - pouca confluencia real",
                      Severidade.ALERTA, ctx.cfg, neutras=len(neutras))
    return _ok("timeframes_conflitantes", titulo,
               "nenhuma camada aponta contra a operacao")


# ---------------------------------------------------------------------------
# 10 - stop muito distante
# ---------------------------------------------------------------------------


def stop_muito_distante(ctx: ContextoAuditoria) -> Checagem:
    titulo = "stop muito distante"
    risco = ctx.op.risco_por_acao
    if risco <= 0 or ctx.op.entry <= 0:
        return _sem_dados("stop_muito_distante", titulo, "sem stop calculavel")

    em_atr = risco / ctx.atr
    em_pct = risco / ctx.op.entry * 100.0
    onde = formata_dinheiro(ctx.op.stop)

    if em_atr >= ctx.cfg.stop_critico_atr or em_pct >= ctx.cfg.stop_critico_pct:
        return _falha("stop_muito_distante", titulo,
                      f"stop em {onde} a {em_atr:.1f} ATR ({em_pct:.2f}% do preco) - "
                      f"o ponto de invalidacao esta longe demais para o setup",
                      Severidade.CRITICO, ctx.cfg, atr=em_atr, pct=em_pct)
    if em_atr >= ctx.cfg.stop_alerta_atr:
        return _falha("stop_muito_distante", titulo,
                      f"stop em {onde} a {em_atr:.1f} ATR - posicao vai sair pequena",
                      Severidade.ALERTA, ctx.cfg, atr=em_atr, pct=em_pct)
    return _ok("stop_muito_distante", titulo,
               f"stop em {onde}, a {em_atr:.1f} ATR ({em_pct:.2f}% do preco)")


# ---------------------------------------------------------------------------
# 11 - expiracao
# ---------------------------------------------------------------------------


def oportunidade_expirada(ctx: ContextoAuditoria) -> Checagem:
    titulo = "oportunidade expirada"
    op = ctx.op
    if op.expires_at is None:
        return _sem_dados("oportunidade_expirada", titulo, "oportunidade sem prazo definido")

    if op.expirada_em(ctx.agora):
        atraso = (ctx.agora - op.expires_at).total_seconds() / 60.0
        return _falha("oportunidade_expirada", titulo,
                      f"a janela terminou as {op.expires_at:%H:%M} "
                      f"({atraso:.0f} min atras)",
                      Severidade.CRITICO, ctx.cfg, atraso_min=atraso)
    restante = (op.expires_at - ctx.agora).total_seconds() / 60.0
    return _ok("oportunidade_expirada", titulo,
               f"valida ate {op.expires_at:%H:%M} ({restante:.0f} min restantes)")


CHECAGENS = (
    resistencia_proxima,
    suporte_proximo,
    baixo_volume,
    divergencias,
    entrada_atrasada,
    risco_retorno_ruim,
    volatilidade_excessiva,
    falso_rompimento,
    timeframes_conflitantes,
    stop_muito_distante,
    oportunidade_expirada,
)
