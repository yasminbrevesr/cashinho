from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from cashinho.domain.risk import RiskProfile


@dataclass(frozen=True, slots=True)
class PaperTicket:
    symbol: str
    side: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    quantity: int
    risk_per_share: Decimal
    monetary_risk: Decimal
    notional: Decimal
    risk_reward: Decimal


@dataclass(frozen=True, slots=True)
class TicketSizing:
    quantity: int
    quantity_by_risk: int
    quantity_by_exposure: int
    risk_per_share: Decimal
    monetary_risk_limit: Decimal
    estimated_risk: Decimal
    notional: Decimal
    limiting_constraint: str


def calculate_ticket_sizing(
    *,
    entry: Decimal,
    stop: Decimal,
    profile: RiskProfile,
    lot_size: int = 1,
) -> TicketSizing:
    """
    Calcula quantidade para a boleta PAPER.

    Limites considerados:
    - risco maximo por operacao;
    - exposicao maxima por ativo;
    - lote padrao de 100 acoes.

    Nao envia nenhuma ordem.
    """

    entry = Decimal(entry)
    stop = Decimal(stop)

    if entry <= 0:
        raise ValueError("Entrada deve ser maior que zero.")

    risk_per_share = abs(entry - stop)

    if risk_per_share <= 0:
        raise ValueError("Entrada e stop nao podem ser iguais.")

    monetary_risk_limit = profile.monetary_risk_per_trade

    # --------------------------------------------------------
    # QUANTIDADE PELO RISCO
    # --------------------------------------------------------

    raw_by_risk = int(
        monetary_risk_limit / risk_per_share
    )

    quantity_by_risk = (
        raw_by_risk // lot_size
    ) * lot_size

    # --------------------------------------------------------
    # QUANTIDADE PELA EXPOSICAO MAXIMA NO ATIVO
    # --------------------------------------------------------

    max_symbol_exposure = (
        profile.capital
        * profile.max_exposure_per_symbol_pct
        / Decimal("100")
    )

    raw_by_exposure = int(
        max_symbol_exposure / entry
    )

    quantity_by_exposure = (
        raw_by_exposure // lot_size
    ) * lot_size

    # --------------------------------------------------------
    # LIMITANTE
    # --------------------------------------------------------

    quantity = min(
        quantity_by_risk,
        quantity_by_exposure,
    )

    if quantity <= 0:
        raise ValueError(
    "Os limites atuais de risco/exposicao nao permitem "
    "nem uma acao.")

    if quantity_by_risk <= quantity_by_exposure:
        limiting_constraint = "RISCO_POR_OPERACAO"
    else:
        limiting_constraint = "EXPOSICAO_POR_ATIVO"

    estimated_risk = (
        risk_per_share * Decimal(quantity)
    ).quantize(Decimal("0.01"))

    notional = (
        entry * Decimal(quantity)
    ).quantize(Decimal("0.01"))

    return TicketSizing(
        quantity=quantity,
        quantity_by_risk=quantity_by_risk,
        quantity_by_exposure=quantity_by_exposure,
        risk_per_share=risk_per_share.quantize(
            Decimal("0.01")
        ),
        monetary_risk_limit=monetary_risk_limit,
        estimated_risk=estimated_risk,
        notional=notional,
        limiting_constraint=limiting_constraint,
    )


def build_paper_ticket(
    *,
    symbol: str,
    side: str,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    quantity: int,
) -> PaperTicket:
    """
    Monta uma ordem simulada.

    Esta funcao NAO possui integracao com MetaTrader.
    """

    entry = Decimal(entry)
    stop = Decimal(stop)
    target = Decimal(target)

    if side not in {"BUY", "SELL"}:
        raise ValueError(
            "Lado invalido. Use BUY ou SELL."
        )

    if quantity <= 0:
        raise ValueError(
            "Quantidade deve ser maior que zero."
        )

    risk_per_share = abs(entry - stop)

    if risk_per_share <= 0:
        raise ValueError(
            "Stop invalido."
        )

    reward_per_share = abs(target - entry)

    risk_reward = (
        reward_per_share / risk_per_share
    ).quantize(Decimal("0.01"))

    monetary_risk = (
        risk_per_share * Decimal(quantity)
    ).quantize(Decimal("0.01"))

    notional = (
        entry * Decimal(quantity)
    ).quantize(Decimal("0.01"))

    return PaperTicket(
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        target=target,
        quantity=quantity,
        risk_per_share=risk_per_share.quantize(
            Decimal("0.01")
        ),
        monetary_risk=monetary_risk,
        notional=notional,
        risk_reward=risk_reward,
    )