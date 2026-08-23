"""O que a agenda faz com uma oportunidade - e o que ela nao consegue fazer.

Tres efeitos, exatamente os pedidos: **reduzir score**, **aumentar risco** e
**bloquear temporariamente**. Nenhum quarto efeito existe, e os tres sao de
mao unica:

- ``ajuste_de_score`` e' sempre **<= 0**. Nao ha caminho para uma notícia
  somar pontos;
- ``multiplicador_de_risco`` e' sempre **>= 1**. Ele so diminui posicao;
- ``bloqueado`` impede operar; nao existe o inverso, um "liberado" que passe
  por cima de outra reprovacao.

E' por isso que uma notícia isolada nao gera BUY nem SELL: a avaliacao nao tem
campo de direcao para preencher. ``directional_bias`` entra so como agravante
quando a operacao vai contra a notícia.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Mapping, Optional, Sequence

from .modelos import AgendaDeEventos, Evento
from .tipos import Disponibilidade, Severidade, TipoDeEvento, ViesDirecional


@dataclass(frozen=True)
class JanelaDeProtecao:
    """Quanto tempo antes e depois do evento a operacao fica bloqueada."""

    antes_min: float = 0.0
    depois_min: float = 0.0

    def pega(self, faltam_min: float) -> bool:
        return -self.depois_min <= faltam_min <= self.antes_min

    def para_dict(self) -> dict:
        return {"antes_min": self.antes_min, "depois_min": self.depois_min}


# Fato relevante nao tem janela "antes": ele nao e' agendado, ele aparece. A
# protecao dele so pode existir depois que ele saiu.
JANELAS_PADRAO: dict[TipoDeEvento, JanelaDeProtecao] = {
    TipoDeEvento.RESULTADOS: JanelaDeProtecao(60, 60),
    TipoDeEvento.DECISAO_DE_JUROS: JanelaDeProtecao(30, 45),
    TipoDeEvento.INFLACAO: JanelaDeProtecao(15, 30),
    TipoDeEvento.PAYROLL: JanelaDeProtecao(15, 30),
    TipoDeEvento.FATO_RELEVANTE: JanelaDeProtecao(0, 120),
    TipoDeEvento.EVENTO_CORPORATIVO: JanelaDeProtecao(0, 0),
}

PENALIDADE_PADRAO: dict[Severidade, float] = {
    Severidade.CRITICA: 25.0,
    Severidade.ALTA: 15.0,
    Severidade.MEDIA: 8.0,
    Severidade.BAIXA: 3.0,
}

RISCO_PADRAO: dict[Severidade, float] = {
    Severidade.CRITICA: 2.0,
    Severidade.ALTA: 1.5,
    Severidade.MEDIA: 1.25,
    Severidade.BAIXA: 1.0,
}


@dataclass(frozen=True)
class ConfigEventos:
    """Os limiares. Todos configuraveis - nada de numero magico escondido."""

    janelas: Mapping[TipoDeEvento, JanelaDeProtecao] = field(
        default_factory=lambda: dict(JANELAS_PADRAO))
    penalidades: Mapping[Severidade, float] = field(
        default_factory=lambda: dict(PENALIDADE_PADRAO))
    multiplicadores: Mapping[Severidade, float] = field(
        default_factory=lambda: dict(RISCO_PADRAO))
    severidade_minima_para_bloquear: Severidade = Severidade.ALTA
    janela_de_atencao_min: float = 240.0
    confianca_minima: float = 0.5
    penalidade_vies_contrario: float = 5.0
    penalidade_maxima: float = 40.0
    sem_fonte_bloqueia: bool = False

    def __post_init__(self) -> None:
        if self.penalidade_maxima < 0:
            raise ValueError("penalidade_maxima nao pode ser negativa")
        if any(v < 0 for v in self.penalidades.values()):
            raise ValueError("penalidade e' desconto: informe valores positivos")
        if any(m < 1 for m in self.multiplicadores.values()):
            raise ValueError(
                "multiplicador de risco menor que 1 deixaria a notícia AUMENTAR a "
                "posicao - este modulo so sabe reduzir")

    def janela(self, tipo: TipoDeEvento) -> JanelaDeProtecao:
        return self.janelas.get(tipo, JanelaDeProtecao())

    def para_dict(self) -> dict:
        return {
            "janelas": {t.value: j.para_dict() for t, j in self.janelas.items()},
            "penalidades": {s.value: v for s, v in self.penalidades.items()},
            "multiplicadores": {s.value: v for s, v in self.multiplicadores.items()},
            "severidade_minima_para_bloquear": self.severidade_minima_para_bloquear.value,
            "janela_de_atencao_min": self.janela_de_atencao_min,
            "confianca_minima": self.confianca_minima,
            "penalidade_maxima": self.penalidade_maxima,
            "sem_fonte_bloqueia": self.sem_fonte_bloqueia,
        }


@dataclass(frozen=True)
class AvaliacaoDeEventos:
    """O que a agenda diz sobre operar este ativo agora."""

    bloqueado: bool = False
    motivo: str = ""
    ajuste_de_score: float = 0.0        # <= 0
    multiplicador_de_risco: float = 1.0  # >= 1
    avisos: tuple[str, ...] = ()
    eventos: tuple[Evento, ...] = ()
    disponibilidade: Disponibilidade = Disponibilidade.SEM_FONTE
    # a agenda que gerou esta avaliacao, para a tela poder mostrar de onde
    # veio; fica fora do para_dict para nao duplicar a lista de eventos
    agenda: Optional[AgendaDeEventos] = None

    def __post_init__(self) -> None:
        # a invariante da camada, garantida no proprio objeto: notícia nao
        # melhora oportunidade e nao aumenta posicao
        if self.ajuste_de_score > 0:
            raise ValueError(
                "ajuste_de_score positivo: uma notícia nao pode somar pontos a uma "
                "oportunidade")
        if self.multiplicador_de_risco < 1:
            raise ValueError(
                "multiplicador de risco menor que 1: uma notícia nao pode aumentar "
                "a posicao")

    @property
    def pesou(self) -> bool:
        return self.bloqueado or bool(self.ajuste_de_score) or self.multiplicador_de_risco > 1

    @property
    def noticias_indisponiveis(self) -> bool:
        return not self.disponibilidade.confiavel

    def para_dict(self) -> dict:
        return {
            "bloqueado": self.bloqueado,
            "motivo": self.motivo,
            "ajuste_de_score": round(self.ajuste_de_score, 2),
            "multiplicador_de_risco": round(self.multiplicador_de_risco, 3),
            "avisos": list(self.avisos),
            "eventos": [e.para_dict() for e in self.eventos],
            "disponibilidade": self.disponibilidade.value,
            "noticias_indisponiveis": self.noticias_indisponiveis,
        }


class PoliticaDeEventos:
    """Traduz a agenda em desconto de score, risco e bloqueio."""

    def __init__(self, config: Optional[ConfigEventos] = None):
        self.config = config or ConfigEventos()

    # ------------------------------------------------------------------
    def avaliar(self, agenda: AgendaDeEventos, symbol: str, instante: datetime,
                direcao=None) -> AvaliacaoDeEventos:
        cfg = self.config

        if not agenda.confiavel:
            motivo = agenda.motivo or agenda.disponibilidade.detalhe
            aviso = f"{agenda.disponibilidade.rotulo}: {motivo}"
            return AvaliacaoDeEventos(
                bloqueado=cfg.sem_fonte_bloqueia,
                motivo=aviso if cfg.sem_fonte_bloqueia else "",
                avisos=(aviso, "sem agenda confiavel nao da para saber se ha evento a vista"),
                disponibilidade=agenda.disponibilidade,
                agenda=agenda,
            )

        proximos = agenda.na_janela(
            instante, cfg.janela_de_atencao_min, cfg.janela_de_atencao_min, symbol)
        if not proximos:
            return AvaliacaoDeEventos(disponibilidade=agenda.disponibilidade, agenda=agenda)

        avisos: list[str] = []
        penalidade = 0.0
        multiplicador = 1.0
        bloqueios: list[str] = []

        for e in proximos:
            faltam = e.minutos_ate(instante)

            # evento nao agendavel (fato relevante) so e' conhecido depois de
            # sair. Deixa-lo pesar antes da hora seria ler o jornal de amanha -
            # o mesmo look-ahead que o resto do robo passa o tempo evitando
            if faltam > 0 and not e.event_type.agendavel:
                continue

            descricao = self._descrever(e, faltam)

            if e.confidence < cfg.confianca_minima:
                avisos.append(f"{descricao} - confianca {e.confidence:.0%} abaixo do "
                              f"minimo de {cfg.confianca_minima:.0%}: registrado, nao aplicado")
                continue

            penalidade += cfg.penalidades.get(e.severity, 0.0)
            if e.contraria(direcao):
                penalidade += cfg.penalidade_vies_contrario
                avisos.append(f"{descricao} - vies {e.directional_bias.rotulo} contra a operacao")
            multiplicador = max(multiplicador, cfg.multiplicadores.get(e.severity, 1.0))

            if self._bloqueia(e, faltam):
                bloqueios.append(descricao)
            else:
                avisos.append(descricao)

        penalidade = min(penalidade, cfg.penalidade_maxima)
        motivo = ""
        if bloqueios:
            motivo = "operacao bloqueada por evento: " + "; ".join(bloqueios)

        return AvaliacaoDeEventos(
            bloqueado=bool(bloqueios),
            motivo=motivo,
            ajuste_de_score=-penalidade,
            multiplicador_de_risco=multiplicador,
            avisos=tuple(avisos),
            eventos=tuple(proximos),
            disponibilidade=agenda.disponibilidade,
            agenda=agenda,
        )

    # ------------------------------------------------------------------
    def _bloqueia(self, evento: Evento, faltam_min: float) -> bool:
        cfg = self.config
        if evento.severity.peso < cfg.severidade_minima_para_bloquear.peso:
            return False
        if not evento.confirmado:
            # data provavel nao para o robo: vira aviso
            return False
        return cfg.janela(evento.event_type).pega(faltam_min)

    def _descrever(self, evento: Evento, faltam_min: float) -> str:
        quando = (f"em {faltam_min:.0f} min" if faltam_min >= 0
                  else f"ha {abs(faltam_min):.0f} min")
        titulo = f" ({evento.titulo})" if evento.titulo else ""
        return (f"{evento.event_type.curto} {evento.alvo} {quando}"
                f"{titulo} · severidade {evento.severity.rotulo} · fonte {evento.source}")


def risco_ajustado(config_risco, avaliacao: AvaliacaoDeEventos):
    """Aplica o multiplicador ao risco por trade - **reduzindo** a posicao.

    O nome engana se lido rapido: "aumentar o risco do evento" significa
    arriscar MENOS dinheiro nele. O multiplicador divide o percentual de risco
    por operacao.
    """
    if avaliacao.multiplicador_de_risco <= 1:
        return config_risco
    return replace(
        config_risco,
        risco_por_trade_pct=config_risco.risco_por_trade_pct / avaliacao.multiplicador_de_risco,
    )


class AvaliadorDeEventos:
    """Junta fonte e politica: e' o que o Opportunity Engine recebe.

    A agenda e' carregada uma vez e reaproveitada - em backtest e replay o
    motor chama isto a cada candle, e reler o arquivo em cada chamada custaria
    mais que todo o resto do pipeline junto. ``recarregar()`` forca releitura.
    """

    def __init__(self, fonte, politica: Optional[PoliticaDeEventos] = None):
        self.fonte = fonte
        self.politica = politica or PoliticaDeEventos()
        self._agenda: Optional[AgendaDeEventos] = None

    @property
    def config(self) -> ConfigEventos:
        return self.politica.config

    def agenda(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        if self._agenda is None:
            self._agenda = self.fonte.carregar(instante)
        return self._agenda

    def recarregar(self, instante: Optional[datetime] = None) -> AgendaDeEventos:
        self._agenda = self.fonte.carregar(instante)
        return self._agenda

    def avaliar(self, symbol: str, instante: datetime, direcao=None) -> AvaliacaoDeEventos:
        return self.politica.avaliar(self.agenda(instante), symbol, instante, direcao)
