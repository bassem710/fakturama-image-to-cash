"""Money math used by the spec. Everything is Decimal; floats never touch money."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ONE_HUNDRED = Decimal(100)


def round_money(amount: Decimal) -> Decimal:
    """Round to two decimal places, half away from zero (commercial rounding)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def gross_master_price(unit_net_price: Decimal, vat_percent: Decimal) -> Decimal:
    """Spec 3.9: Product master gross price. The line discount is deliberately NOT applied."""
    return round_money(unit_net_price * (1 + vat_percent / ONE_HUNDRED))


def line_net_price(quantity: Decimal, unit_net_price: Decimal, discount_percent: Decimal) -> Decimal:
    """Spec 3.16: line Price = quantity x unit net price x (1 - discount / 100)."""
    return round_money(quantity * unit_net_price * (1 - discount_percent / ONE_HUNDRED))


def vat_amount(net_amount: Decimal, vat_percent: Decimal) -> Decimal:
    return round_money(net_amount * vat_percent / ONE_HUNDRED)


def amounts_match(expected: Decimal, observed: Decimal, tolerance: Decimal = CENT) -> bool:
    return abs(expected - observed) <= tolerance
