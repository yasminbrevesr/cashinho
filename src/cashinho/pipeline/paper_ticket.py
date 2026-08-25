from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
    timeframe: str | None = None


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
    - lote fracionario de uma unidade por padrao.

    Nao envia nenhuma ordem.
    """

    entry = Decimal(entry)
    stop = Decimal(stop)

    if lot_size <= 0:
        raise ValueError("Lote deve ser maior que zero.")

    if entry <= 0:
        raise ValueError("Entrada deve ser maior que zero.")

    risk_per_share = abs(entry - stop)

    if risk_per_share <= 0:
        raise ValueError("Entrada e stop nao podem ser iguais.")

    monetary_risk_limit = profile.monetary_risk_per_trade

    # --------------------------------------------------------
    # QUANTIDADE PELO RISCO
    # --------------------------------------------------------

    raw_by_risk = int(monetary_risk_limit / risk_per_share)

    quantity_by_risk = (raw_by_risk // lot_size) * lot_size

    # --------------------------------------------------------
    # QUANTIDADE PELA EXPOSICAO MAXIMA NO ATIVO
    # --------------------------------------------------------

    max_symbol_exposure = profile.capital * profile.max_exposure_per_symbol_pct / Decimal("100")

    raw_by_exposure = int(max_symbol_exposure / entry)

    quantity_by_exposure = (raw_by_exposure // lot_size) * lot_size

    # --------------------------------------------------------
    # LIMITANTE
    # --------------------------------------------------------

    quantity = min(
        quantity_by_risk,
        quantity_by_exposure,
    )

    if quantity <= 0:
        raise ValueError("Os limites atuais de risco/exposicao nao permitem nem uma acao.")

    if quantity_by_risk <= quantity_by_exposure:
        limiting_constraint = "RISCO_POR_OPERACAO"
    else:
        limiting_constraint = "EXPOSICAO_POR_ATIVO"

    estimated_risk = (risk_per_share * Decimal(quantity)).quantize(Decimal("0.01"))

    notional = (entry * Decimal(quantity)).quantize(Decimal("0.01"))

    return TicketSizing(
        quantity=quantity,
        quantity_by_risk=quantity_by_risk,
        quantity_by_exposure=quantity_by_exposure,
        risk_per_share=risk_per_share.quantize(Decimal("0.01")),
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
    min_risk_reward: Decimal = Decimal("1"),
    maximum_quantity: int | None = None,
    timeframe: str | None = None,
) -> PaperTicket:
    """
    Monta uma ordem simulada.

    Esta funcao NAO possui integracao com MetaTrader.
    """

    entry = Decimal(entry)
    stop = Decimal(stop)
    target = Decimal(target)

    if side not in {"BUY", "SELL"}:
        raise ValueError("Lado invalido. Use BUY ou SELL.")

    if quantity <= 0:
        raise ValueError("Quantidade deve ser maior que zero.")

    if entry <= 0 or stop <= 0 or target <= 0:
        raise ValueError("Entrada, stop e alvo devem ser maiores que zero.")

    if side == "BUY" and not (stop < entry < target):
        raise ValueError("Geometria BUY invalida: stop < entrada < alvo.")
    if side == "SELL" and not (target < entry < stop):
        raise ValueError("Geometria SELL invalida: alvo < entrada < stop.")
    if maximum_quantity is not None and quantity > maximum_quantity:
        raise ValueError("Quantidade acima do maximo permitido pelo Risk Manager.")

    risk_per_share = abs(entry - stop)

    if risk_per_share <= 0:
        raise ValueError("Stop invalido.")

    reward_per_share = abs(target - entry)

    risk_reward = (reward_per_share / risk_per_share).quantize(Decimal("0.01"))

    if risk_reward < min_risk_reward:
        raise ValueError(f"R:R {risk_reward} abaixo do minimo permitido ({min_risk_reward}).")

    monetary_risk = (risk_per_share * Decimal(quantity)).quantize(Decimal("0.01"))

    notional = (entry * Decimal(quantity)).quantize(Decimal("0.01"))

    return PaperTicket(
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        target=target,
        quantity=quantity,
        risk_per_share=risk_per_share.quantize(Decimal("0.01")),
        monetary_risk=monetary_risk,
        notional=notional,
        risk_reward=risk_reward,
        timeframe=timeframe,
    )
