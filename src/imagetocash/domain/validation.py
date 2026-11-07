"""Spec 1.1 "extract and normalize": prove the extracted numbers are internally consistent
before Fakturama is touched. The same rules are checked again on screen at 3.16 and 4.3."""

from collections import defaultdict
from decimal import Decimal

from imagetocash.domain.models import Address, OrderDocument
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
        problems.append(f"gross total: {order.totals.net} + {order.totals.vat} != {order.totals.gross} on the image")
    if order.payment.is_paid and order.payment.payment_date is None:
        problems.append("paid status is PAID but no payment date was found")
    return problems


def ensure_order_is_consistent(order: OrderDocument) -> None:
    problems = find_inconsistencies(order)
    if problems:
        raise ManualReviewRequired("1.1", ReviewReason.TOTALS_MISMATCH, "; ".join(problems))


def _address_complete(address: Address) -> bool:
    return all(v.strip() for v in (address.street, address.zip_code, address.city, address.country))


def required_fields_missing(order: OrderDocument) -> list[str]:
    """Spec 1.2: the fields the rest of the flow cannot do without (blank = missing)."""
    debtor = order.debtor
    checks = {
        "External Reference": bool(order.external_reference.strip()),
        "Company or customer name": bool(debtor.search_text.strip()),
        "billing street / ZIP / City / Country": _address_complete(debtor.billing_address),
        "Payment Method": bool(order.payment.method.strip()),
        "Paid Status": bool(order.payment.paid_status.strip()),
    }
    if not debtor.billing_equals_delivery:  # a separate delivery address is filled in too (2.7)
        checks["delivery street / ZIP / City / Country"] = _address_complete(debtor.delivery_address)
    missing = [name for name, present in checks.items() if not present]
    for item in order.items:
        if not item.sku.strip():
            missing.append(f"item {item.position} SKU")
        if not item.description.strip():  # becomes the Product name (3.8)
            missing.append(f"item {item.position} description")
    return missing


def ensure_required_fields(order: OrderDocument) -> None:
    missing = required_fields_missing(order)
    if missing:
        raise ManualReviewRequired("1.2", ReviewReason.EXTRACTION_INVALID, "missing: " + ", ".join(missing))
