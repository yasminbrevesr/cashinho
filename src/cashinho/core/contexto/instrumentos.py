"""O catalogo de instrumentos do contexto - e de onde cada um vem.

A regra deste arquivo e' a mais importante do modulo: **um instrumento so
existe aqui com a fonte declarada**. Quando nao ha fonte que de para usar de
forma confiavel, o instrumento continua no catalogo, mas marcado como
``FONTE A CONFIRMAR`` - e nunca recebe numero.

Estimar minerio de ferro a partir de VALE3, por exemplo, seria facil e
pareceria util. Seria tambem uma cotacao inventada com cara de dado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional


class Papel(str, Enum):
    """Para que serve o instrumento na leitura de contexto."""

    INDICE_LOCAL = "indice_local"
    CAMBIO = "cambio"
    JUROS = "juros"
    COMMODITY = "commodity"
    INDICE_INTERNACIONAL = "indice_internacional"

    @property
    def rotulo(self) -> str:
        return {
            "indice_local": "Indice local",
            "cambio": "Cambio",
            "juros": "Juros",
            "commodity": "Commodity",
            "indice_internacional": "Indice internacional",
        }[self.value]


@dataclass(frozen=True)
class Instrumento:
    """Um item do contexto, com a fonte declarada por nome."""

    chave: str
    nome: str
    papel: Papel
    tickers: Mapping[str, str] = field(default_factory=dict)  # fonte -> ticker
    intradiario: bool = True
    unidade: str = ""
    casas: int = 2
    observacao: str = ""

    @property
    def tem_fonte(self) -> bool:
        """Existe alguma fonte declarada para este instrumento?"""
        return bool(self.tickers)

    def ticker(self, fonte: str) -> Optional[str]:
        return self.tickers.get(fonte)

    def para_dict(self) -> dict:
        return {
            "chave": self.chave,
            "nome": self.nome,
            "papel": self.papel.value,
            "fontes": sorted(self.tickers),
            "intradiario": self.intradiario,
            "tem_fonte": self.tem_fonte,
            "observacao": self.observacao,
        }


# ---------------------------------------------------------------------------
# O catalogo. Ampliar e' so acrescentar uma linha - com a fonte junto.
# ---------------------------------------------------------------------------

IBOVESPA = Instrumento(
    "ibovespa", "Ibovespa", Papel.INDICE_LOCAL,
    tickers={"yahoo": "^BVSP"}, unidade="pts", casas=0,
)

DOLAR = Instrumento(
    "dolar", "Dolar (USD/BRL)", Papel.CAMBIO,
    tickers={"yahoo": "USDBRL=X"}, unidade="R$", casas=4,
)

JUROS_CDI = Instrumento(
    "juros", "Juros (CDI ao ano)", Papel.JUROS,
    tickers={"bcb": "12"},  # serie 12 do SGS: CDI diario
    intradiario=False, unidade="% a.a.", casas=2,
    observacao="serie diaria do Banco Central: muda uma vez por dia, nao intradiario",
)

PETROLEO = Instrumento(
    "petroleo", "Petroleo (Brent)", Papel.COMMODITY,
    tickers={"yahoo": "BZ=F"}, unidade="US$", casas=2,
    observacao="futuro continuo: a rolagem de contrato aparece como salto no historico",
)

MINERIO = Instrumento(
    "minerio", "Minerio de ferro", Papel.COMMODITY,
    tickers={},  # <- de proposito
    unidade="US$/t",
    observacao=(
        "FONTE A CONFIRMAR: o preco de referencia (Platts/SGX) e' pago e nao tem "
        "fonte publica confiavel. Derivar de VALE3 seria inventar cotacao"
    ),
)

SP500 = Instrumento(
    "sp500", "S&P 500", Papel.INDICE_INTERNACIONAL,
    tickers={"yahoo": "^GSPC"}, unidade="pts", casas=0,
)

NASDAQ = Instrumento(
    "nasdaq", "Nasdaq Composite", Papel.INDICE_INTERNACIONAL,
    tickers={"yahoo": "^IXIC"}, unidade="pts", casas=0,
)

CATALOGO: tuple[Instrumento, ...] = (
    IBOVESPA, DOLAR, JUROS_CDI, PETROLEO, MINERIO, SP500, NASDAQ,
)

POR_CHAVE: dict[str, Instrumento] = {i.chave: i for i in CATALOGO}


def instrumento(chave: str) -> Instrumento:
    try:
        return POR_CHAVE[chave]
    except KeyError:
        raise KeyError(
            f"instrumento desconhecido: {chave!r} (conhecidos: {', '.join(sorted(POR_CHAVE))})"
        ) from None


def sem_fonte_confiavel() -> tuple[Instrumento, ...]:
    """Os instrumentos que o catalogo assume nao saber medir."""
    return tuple(i for i in CATALOGO if not i.tem_fonte)
