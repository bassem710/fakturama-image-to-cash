"""Spec 1.1 "extract and normalize": prove the extracted numbers are internally consistent
before Fakturama is touched. The same rules are checked again on screen at 3.16 and 4.3."""

from collections import defaultdict
from decimal import Decimal

from imagetocash.domain.models import OrderDocument
from imagetocash.domain.pricing import CENT, amounts_match, line_net_price, round_money, vat_amount
from imagetocash.domain.review import ManualReviewRequired, ReviewReason


def find_inconsistencies(order: OrderDocument) -> list[str]:
    problems: list[str] = []
    if not order.items:
        problems.append("order has no items")
    if not order.external_reference.strip():
        problems.append("external reference is empty")

    for item in order.items:
        expected = line_net_price(item.quantity, item.unit_net_price, item.discount_percent)
        if not amounts_match(expected, item.source_line_total):
            problems.append(
                f"line {item.position} ({item.sku}): {item.quantity} x {item.unit_net_price} "
                f"- {item.discount_percent}% = {expected}, image says {item.source_line_total}"
            )

    lines_net = sum((i.source_line_total for i in order.items), Decimal(0))
    expected_net = round_money(lines_net * (1 - order.order_discount_percent / 100) + order.shipping_net)
    if not amounts_match(expected_net, order.totals.net):
        problems.append(f"net total: lines give {expected_net}, image says {order.totals.net}")

    # VAT is computed per rate, like an invoice; allow one cent of rounding per rate.
    net_by_rate: dict[Decimal, Decimal] = defaultdict(Decimal)
    for item in order.items:
        net_by_rate[item.vat_percent] += item.source_line_total
    expected_vat = sum((vat_amount(net, rate) for rate, net in net_by_rate.items()), Decimal(0))
    if order.order_discount_percent == 0 and order.shipping_net == 0:
        tolerance = CENT * max(1, len(net_by_rate))
        if not amounts_match(expected_vat, order.totals.vat, tolerance):
            problems.append(f"VAT total: rates give {expected_vat}, image says {order.totals.vat}")

    if not amounts_match(order.totals.net + order.totals.vat, order.totals.gross):
        problems.append(
            f"gross total: {order.totals.net} + {order.totals.vat} != {order.totals.gross} on the image"
        )
    if order.payment.is_paid and order.payment.payment_date is None:
        problems.append("paid status is PAID but no payment date was found")
    return problems


def ensure_order_is_consistent(order: OrderDocument) -> None:
    problems = find_inconsistencies(order)
    if problems:
        raise ManualReviewRequired("1.1", ReviewReason.TOTALS_MISMATCH, "; ".join(problems))
