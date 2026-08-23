"""Traduz uma Opportunity aprovada em boletas para digitar na Genial.

**Este modulo nao envia nada.** Ele nao conhece API, token nem endpoint da
Genial - e nao deve conhecer nesta etapa. O que ele produz e' um roteiro de
digitacao: que tipo de boleta abrir e que valor colocar em cada campo.

A escolha do TIPO e' logica de mercado, e vale em qualquer corretora:

- entrada acima do preco atual -> **Compra Stop** (rompimento);
- entrada abaixo ou igual -> **Compra** (limitada, pullback);
- venda espelha os dois casos;
- protecao de uma compra: stop vira **Venda Stop**, alvo vira **Venda**.

O que NAO e' logica de mercado - como a Genial nomeia e trata cada campo -
sai marcado como ``REGRA GENIAL A CONFIRMAR``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from ...models import Direction, arredonda_tick, formata_dinheiro
from ..oportunidade.estados import EstadoOportunidade
from ..oportunidade.modelos import Opportunity
from ..risk.models import RiskDecision
from .modelos import Boleta, CampoBoleta, PapelDaBoleta, ResumoOperacao, Ticket, TipoBoleta
from .regras import PENDENCIAS_GENIAL, Regra


@dataclass(frozen=True)
class ConfigTicket:
    """Ajustes da traducao. Nada aqui e' regra da Genial - sao escolhas nossas."""

    tick: float = 0.01
    ticks_de_offset: int = 2  # distancia entre disparo e limite numa ordem stop
    validade: str = "Dia"
    lote: int = 100
    usar_oco_para_protecao: bool = True

    def __post_init__(self) -> None:
        if self.tick <= 0:
            raise ValueError("tick precisa ser maior que zero")
        if self.ticks_de_offset < 0:
            raise ValueError("ticks_de_offset nao pode ser negativo")

    @property
    def offset(self) -> float:
        return round(self.ticks_de_offset * self.tick, 10)


def _preco(valor: float) -> str:
    """Formato de digitacao: 31,05 (sem 'R$', que a boleta nao aceita)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class TicketGenerator:
    """Gera as boletas de uma oportunidade aprovada. Nao envia ordem."""

    envia_ordem = False  # explicito: esta etapa e' so traducao

    def __init__(self, config: Optional[ConfigTicket] = None):
        self.config = config or ConfigTicket()

    # ------------------------------------------------------------------
    def gerar(
        self,
        op: Opportunity,
        decisao: Optional[RiskDecision] = None,
        quantidade: Optional[int] = None,
        preco_atual: Optional[float] = None,
    ) -> Ticket:
        """Traduz a oportunidade. Sem aprovacao, nao gera boleta."""
        if op.estado is not EstadoOportunidade.APROVADO:
            return Ticket(
                gerado=False,
                motivo=f"a oportunidade esta como {op.estado.value} - "
                       f"a boleta so e' gerada para setup aprovado",
                pendencias=PENDENCIAS_GENIAL,
            )
        if decisao is not None and not decisao.allowed:
            return Ticket(
                gerado=False,
                motivo=f"o Risk Manager recusou: {decisao.reason}",
                pendencias=PENDENCIAS_GENIAL,
            )

        qtd = quantidade if quantidade is not None else (
            decisao.position_size if decisao is not None else 0
        )
        if qtd <= 0:
            return Ticket(
                gerado=False,
                motivo="sem quantidade: passe a decisao do Risk Manager ou informe a quantidade",
                pendencias=PENDENCIAS_GENIAL,
            )

        referencia = preco_atual if preco_atual is not None else op.entry
        entrada = arredonda_tick(op.entry, self.config.tick)
        stop = arredonda_tick(op.stop, self.config.tick)
        alvo = arredonda_tick(op.target, self.config.tick)
        alta = op.direction is Direction.LONG

        tipo_entrada = self._tipo_de_entrada(alta, entrada, referencia)
        boletas = [self._boleta_de_entrada(op, qtd, entrada, tipo_entrada, alta)]
        if self.config.usar_oco_para_protecao:
            boletas.append(self._boleta_oco(op, qtd, stop, alvo, alta))
        else:
            boletas.append(self._boleta_de_stop(op, qtd, stop, alta))
            boletas.append(self._boleta_de_alvo(op, qtd, alvo, alta))

        risco = abs(entrada - stop) * qtd
        retorno = abs(alvo - entrada) * qtd
        resumo = ResumoOperacao(
            ativo=op.symbol,
            entrada=entrada, stop=stop, alvo=alvo, quantidade=qtd,
            risco_monetario=risco, retorno_potencial=retorno,
            rr=(retorno / risco) if risco else 0.0,
            score=op.score, setup=op.setup, status=op.estado.value,
            timestamp=op.timestamp, direcao=op.direction,
        )

        return Ticket(
            gerado=True,
            resumo=resumo,
            boletas=tuple(boletas),
            entrar_somente_se=self._entrar_somente_se(op, entrada, tipo_entrada, alta),
            cancelar_se=self._cancelar_se(op, stop, alta),
            pendencias=PENDENCIAS_GENIAL,
            avisos=self._avisos(op, qtd, decisao),
        )

    # ------------------------------------------------------------------
    # boletas
    # ------------------------------------------------------------------
    def _tipo_de_entrada(self, alta: bool, entrada: float, referencia: float) -> TipoBoleta:
        """Rompimento vira Stop; pullback vira ordem limitada."""
        if alta:
            return TipoBoleta.COMPRA_STOP if entrada > referencia else TipoBoleta.COMPRA
        return TipoBoleta.VENDA_STOP if entrada < referencia else TipoBoleta.VENDA

    def _boleta_de_entrada(self, op: Opportunity, qtd: int, entrada: float,
                           tipo: TipoBoleta, alta: bool) -> Boleta:
        cfg = self.config
        campos = [self._campo_ativo(op.symbol, qtd), self._campo_quantidade(qtd),
                  self._campo_validade()]

        if tipo.eh_stop:
            # numa compra stop o limite fica ACIMA do disparo, para nao ficar
            # sem execucao quando o preco passa rapido; na venda stop, abaixo
            limite = entrada + cfg.offset if alta else entrada - cfg.offset
            campos.append(CampoBoleta(
                "Preco de disparo", _preco(entrada), entrada, confirmado=False,
                observacao="nome e existencia do campo de disparo precisam ser conferidos",
                regra_chave="campo_preco",
            ))
            campos.append(CampoBoleta(
                "Preco", _preco(arredonda_tick(limite, cfg.tick)),
                arredonda_tick(limite, cfg.tick), confirmado=False,
                observacao="assumido como o preco LIMITE da ordem stop",
                regra_chave="campo_preco",
            ))
            campos.append(CampoBoleta(
                "Offset", _preco(cfg.offset), cfg.offset, confirmado=False,
                observacao=f"aqui: distancia disparo-limite ({cfg.ticks_de_offset} ticks). "
                           "O significado do campo na Genial precisa ser confirmado",
                regra_chave="offset",
            ))
        else:
            campos.append(CampoBoleta(
                "Preco", _preco(entrada), entrada,
                observacao="preco limite da ordem",
            ))
            campos.append(CampoBoleta(
                "Offset", "-", None, confirmado=False,
                observacao="nao se aplica a ordem limitada; confirmar se a boleta exibe o campo",
                regra_chave="offset",
            ))

        campos.append(self._campo_a_mercado(False))
        campos.append(CampoBoleta("OCO", "nao", None, confirmado=False,
                                  observacao="a protecao vai na boleta seguinte",
                                  regra_chave="oco"))
        campos.append(CampoBoleta("Gain", "-", None, confirmado=False,
                                  observacao="preenchido apenas na boleta OCO", regra_chave="oco"))
        campos.append(CampoBoleta("Loss", "-", None, confirmado=False,
                                  observacao="preenchido apenas na boleta OCO", regra_chave="oco"))

        explicacao = (
            f"entrada por rompimento: a ordem so dispara se o preco negociar "
            f"{'acima' if alta else 'abaixo'} de {_preco(entrada)}"
            if tipo.eh_stop else
            f"entrada limitada: executa em {_preco(entrada)} ou melhor"
        )
        return Boleta(tipo, PapelDaBoleta.ENTRADA, tuple(campos), explicacao)

    def _boleta_oco(self, op: Opportunity, qtd: int, stop: float, alvo: float,
                    alta: bool) -> Boleta:
        """Protecao em uma boleta so: Gain no alvo, Loss no stop."""
        tipo = TipoBoleta.VENDA if alta else TipoBoleta.COMPRA
        campos = [
            self._campo_ativo(op.symbol, qtd),
            self._campo_quantidade(qtd),
            self._campo_validade(),
            CampoBoleta("Preco", "-", None, confirmado=False,
                        observacao="na OCO os precos vao em Gain e Loss; confirmar se a boleta "
                                   "ainda pede um preco principal",
                        regra_chave="oco"),
            self._campo_a_mercado(False),
            CampoBoleta("OCO", "sim", None, confirmado=False,
                        observacao="confirmar se a OCO exige posicao ja aberta ou pode ser "
                                   "enviada junto com a entrada",
                        regra_chave="oco"),
            CampoBoleta("Gain", _preco(alvo), alvo, confirmado=False,
                        observacao="preco do alvo; confirmar se a Genial espera preco absoluto "
                                   "ou distancia",
                        regra_chave="oco"),
            CampoBoleta("Loss", _preco(stop), stop, confirmado=False,
                        observacao="preco do stop; confirmar se a Genial espera preco absoluto "
                                   "ou distancia",
                        regra_chave="oco"),
            CampoBoleta("Offset", _preco(self.config.offset), self.config.offset,
                        confirmado=False,
                        observacao="usado quando a perna de Loss dispara e vira ordem limitada",
                        regra_chave="offset"),
        ]
        explicacao = (
            f"protecao da posicao: realiza em {_preco(alvo)} ou encerra em {_preco(stop)} - "
            f"quando uma perna executa, a outra e' cancelada"
        )
        return Boleta(tipo, PapelDaBoleta.OCO, tuple(campos), explicacao)

    def _boleta_de_stop(self, op: Opportunity, qtd: int, stop: float, alta: bool) -> Boleta:
        tipo = TipoBoleta.VENDA_STOP if alta else TipoBoleta.COMPRA_STOP
        limite = stop - self.config.offset if alta else stop + self.config.offset
        campos = [
            self._campo_ativo(op.symbol, qtd), self._campo_quantidade(qtd), self._campo_validade(),
            CampoBoleta("Preco de disparo", _preco(stop), stop, confirmado=False,
                        observacao="dispara a protecao", regra_chave="campo_preco"),
            CampoBoleta("Preco", _preco(arredonda_tick(limite, self.config.tick)),
                        arredonda_tick(limite, self.config.tick), confirmado=False,
                        observacao="limite depois do disparo", regra_chave="campo_preco"),
            self._campo_a_mercado(False),
            CampoBoleta("OCO", "nao", None, confirmado=False, regra_chave="oco",
                        observacao="stop e alvo em boletas separadas"),
            CampoBoleta("Gain", "-", None, confirmado=False, regra_chave="oco"),
            CampoBoleta("Loss", "-", None, confirmado=False, regra_chave="oco"),
            CampoBoleta("Offset", _preco(self.config.offset), self.config.offset,
                        confirmado=False, regra_chave="offset",
                        observacao="distancia disparo-limite"),
        ]
        return Boleta(tipo, PapelDaBoleta.STOP, tuple(campos),
                      f"encerra a posicao se o preco atingir {_preco(stop)}")

    def _boleta_de_alvo(self, op: Opportunity, qtd: int, alvo: float, alta: bool) -> Boleta:
        tipo = TipoBoleta.VENDA if alta else TipoBoleta.COMPRA
        campos = [
            self._campo_ativo(op.symbol, qtd), self._campo_quantidade(qtd), self._campo_validade(),
            CampoBoleta("Preco", _preco(alvo), alvo, observacao="preco de realizacao"),
            self._campo_a_mercado(False),
            CampoBoleta("OCO", "nao", None, confirmado=False, regra_chave="oco"),
            CampoBoleta("Gain", "-", None, confirmado=False, regra_chave="oco"),
            CampoBoleta("Loss", "-", None, confirmado=False, regra_chave="oco"),
            CampoBoleta("Offset", "-", None, confirmado=False, regra_chave="offset"),
        ]
        return Boleta(tipo, PapelDaBoleta.ALVO, tuple(campos),
                      f"realiza a posicao em {_preco(alvo)}")

    # ------------------------------------------------------------------
    # campos comuns
    # ------------------------------------------------------------------
    def _campo_ativo(self, symbol: str, qtd: int) -> CampoBoleta:
        fracionario = qtd % self.config.lote != 0
        return CampoBoleta(
            "Ativo", symbol.upper(), None, confirmado=not fracionario,
            observacao=(
                f"quantidade fora do lote de {self.config.lote}: pode exigir o ticker "
                f"fracionario ({symbol.upper()}F). Confirmar como a Genial roteia"
                if fracionario else ""
            ),
            regra_chave="quantidade_fracionario" if fracionario else "",
        )

    def _campo_quantidade(self, qtd: int) -> CampoBoleta:
        return CampoBoleta("Quantidade", str(qtd), float(qtd),
                           observacao="quantidade autorizada pelo Risk Manager")

    def _campo_validade(self) -> CampoBoleta:
        return CampoBoleta(
            "Validade", self.config.validade, None, confirmado=False,
            observacao="rotulo assumido para validade de um dia; conferir as opcoes da plataforma",
            regra_chave="validade",
        )

    def _campo_a_mercado(self, marcado: bool) -> CampoBoleta:
        return CampoBoleta(
            "A Mercado", "sim" if marcado else "nao", None, confirmado=False,
            observacao="confirmar se marcar desabilita o campo Preco e como a Genial protege "
                       "a execucao",
            regra_chave="a_mercado",
        )

    # ------------------------------------------------------------------
    # condicoes
    # ------------------------------------------------------------------
    def _entrar_somente_se(self, op: Opportunity, entrada: float, tipo: TipoBoleta,
                           alta: bool) -> tuple[str, ...]:
        """As condicoes precisam falar do MESMO tipo de boleta que foi gerada."""
        condicoes = []
        if tipo.eh_stop:
            condicoes.append(
                f"o preco negociar {'acima' if alta else 'abaixo'} de {_preco(entrada)} "
                f"(e' o que dispara a boleta)"
            )
        else:
            condicoes.append(
                f"o preco recuar ate {_preco(entrada)} sem antes perder {_preco(op.stop)}"
            )

        leitura = op.leitura
        if leitura is not None:
            for papel in ("context", "trend"):
                camada = leitura.camada(papel)
                if camada is not None:
                    condicoes.append(
                        f"o {camada.timeframe} continuar {camada.valor} quando voce for digitar"
                    )
        if op.expires_at is not None:
            condicoes.append(f"ainda estiver dentro da validade, ate {op.expires_at:%H:%M}")
        condicoes.append("o pregao estiver em horario normal, fora de leilao")
        return tuple(condicoes)

    def _cancelar_se(self, op: Opportunity, stop: float, alta: bool) -> tuple[str, ...]:
        condicoes = [f"o preco fechar {'abaixo' if alta else 'acima'} de {_preco(stop)} "
                     f"antes de a entrada disparar"]
        if op.expires_at is not None:
            condicoes.append(f"passar de {op.expires_at:%H:%M} sem a entrada ter disparado")
        if op.invalidation and op.invalidation != "-":
            condicoes.append(op.invalidation)
        leitura = op.leitura
        if leitura is not None:
            trend = leitura.camada("trend")
            if trend is not None:
                condicoes.append(f"a leitura de {trend.timeframe} deixar de ser {trend.valor}")
        condicoes.append("sair noticia relevante do ativo ou do mercado")
        return tuple(dict.fromkeys(condicoes))

    def _avisos(self, op: Opportunity, qtd: int, decisao: Optional[RiskDecision]) -> tuple[str, ...]:
        avisos = ["este modulo NAO envia ordem: os valores sao para digitacao manual"]
        if qtd % self.config.lote != 0:
            avisos.append(
                f"{qtd} acoes nao fecham lote de {self.config.lote} - parte vai para o fracionario"
            )
        if decisao is None:
            avisos.append("quantidade informada na mao, sem passar pelo Risk Manager desta vez")
        avisos.extend(op.warnings)
        return tuple(dict.fromkeys(avisos))
