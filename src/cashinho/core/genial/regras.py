"""O que se sabe e o que falta confirmar sobre a boleta da Genial.

Este arquivo existe por uma razao so: **nao inventar**. O Cashinho calcula os
precos e as quantidades - isso e' dele. Como a boleta da Genial se comporta
e' da Genial, e nada aqui foi verificado contra a documentacao deles.

Separacao:

- ``REGRAS_B3`` - regras de mercado, valem para qualquer corretora e podem
  ser usadas com seguranca (tick de R$ 0,01 em acoes, lote padrao de 100);
- ``PENDENCIAS_GENIAL`` - tudo o que depende de como a plataforma da Genial
  se comporta. Cada item diz o que o sistema **assumiu** e o que precisa ser
  confirmado. Enquanto nao houver confirmacao, a tela mostra
  ``REGRA GENIAL A CONFIRMAR`` ao lado do campo.

Confirmou alguma? Troque ``status`` para ``CONFIRMADA`` e preencha ``fonte``
com onde a informacao foi verificada.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StatusRegra(str, Enum):
    CONFIRMADA = "confirmada"
    A_CONFIRMAR = "a confirmar"

    @property
    def pendente(self) -> bool:
        return self is StatusRegra.A_CONFIRMAR


@dataclass(frozen=True)
class Regra:
    """Uma regra de preenchimento, confirmada ou nao."""

    chave: str
    titulo: str
    assumido: str  # o que o sistema faz hoje
    confirmar: str = ""  # o que precisa ser verificado
    status: StatusRegra = StatusRegra.A_CONFIRMAR
    fonte: str = ""  # onde foi confirmado, quando for

    @property
    def pendente(self) -> bool:
        return self.status.pendente

    @property
    def selo(self) -> str:
        return "REGRA GENIAL A CONFIRMAR" if self.pendente else f"confirmado: {self.fonte}"

    def para_dict(self) -> dict:
        return {
            "chave": self.chave,
            "titulo": self.titulo,
            "assumido": self.assumido,
            "confirmar": self.confirmar,
            "status": self.status.value,
            "fonte": self.fonte,
        }


# ---------------------------------------------------------------------------
# regras de mercado - independem da corretora
# ---------------------------------------------------------------------------

REGRAS_B3: tuple[Regra, ...] = (
    Regra(
        chave="tick",
        titulo="variacao minima de preco",
        assumido="R$ 0,01 para acoes no mercado a vista; todos os precos sao arredondados a isso",
        status=StatusRegra.CONFIRMADA,
        fonte="regra de mercado da B3, nao depende da corretora",
    ),
    Regra(
        chave="lote",
        titulo="lote padrao",
        assumido="100 acoes no lote padrao; quantidades fora disso vao para o fracionario",
        status=StatusRegra.CONFIRMADA,
        fonte="regra de mercado da B3, nao depende da corretora",
    ),
)


# ---------------------------------------------------------------------------
# tudo o que depende da plataforma da Genial
# ---------------------------------------------------------------------------

PENDENCIAS_GENIAL: tuple[Regra, ...] = (
    Regra(
        chave="tipos_boleta",
        titulo="nomes dos tipos de boleta",
        assumido="a boleta oferece Compra, Compra Stop, Venda e Venda Stop com esses nomes",
        confirmar="conferir os nomes exatos na plataforma e se ha outros tipos relevantes "
                  "(ex.: start stop, stop movel)",
    ),
    Regra(
        chave="campo_preco",
        titulo="campo Preco na boleta stop",
        assumido="nas boletas Stop, o preco enviado e' o LIMITE, e o disparo vai em campo proprio",
        confirmar="confirmar se a Genial usa dois campos (disparo e limite) ou apenas um, "
                  "e qual deles se chama 'Preco'",
    ),
    Regra(
        chave="offset",
        titulo="significado do campo Offset",
        assumido="offset e' a distancia em reais entre o disparo e o preco limite",
        confirmar="ESTE E' O CAMPO MAIS AMBIGUO: em algumas plataformas Offset e' a distancia "
                  "disparo-limite, em outras e' a distancia do stop movel. Confirmar antes de usar",
    ),
    Regra(
        chave="a_mercado",
        titulo="checkbox A Mercado",
        assumido="marcar A Mercado ignora o campo Preco e envia a ordem a mercado",
        confirmar="confirmar se a Genial envia a mercado puro ou com preco de protecao, "
                  "e se o campo Preco fica desabilitado",
    ),
    Regra(
        chave="validade",
        titulo="opcoes de validade",
        assumido="existe uma validade para o dia (usada aqui como 'Dia'), adequada a day trade",
        confirmar="confirmar os rotulos disponiveis (Dia, Ate cancelar, Ate a data) e qual e' o padrao",
    ),
    Regra(
        chave="oco",
        titulo="boleta OCO (Gain e Loss)",
        assumido="a OCO recebe um preco de Gain e um de Loss e cancela uma perna quando a outra executa",
        confirmar="confirmar se a OCO exige posicao ja aberta, se pode ser enviada junto com a "
                  "entrada, e se Gain/Loss sao precos absolutos ou distancias",
    ),
    Regra(
        chave="quantidade_fracionario",
        titulo="fracionario na mesma boleta",
        assumido="quantidade fora do lote padrao exige o ticker fracionario (sufixo F)",
        confirmar="confirmar se a Genial roteia sozinha ou se e' preciso trocar o ativo na boleta",
    ),
    Regra(
        chave="custos",
        titulo="corretagem e taxas",
        assumido="os custos usados nas contas sao os configurados no Cashinho, nao os da conta real",
        confirmar="conferir a tabela de corretagem e taxas da sua conta na Genial",
    ),
)

TODAS: tuple[Regra, ...] = REGRAS_B3 + PENDENCIAS_GENIAL


def regra(chave: str) -> Optional[Regra]:
    for r in TODAS:
        if r.chave == chave:
            return r
    return None


def pendentes() -> tuple[Regra, ...]:
    return tuple(r for r in TODAS if r.pendente)
