"""On-screen verifications shared by stages 2-5 ("verify each step before moving to the next")."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from imagetocash.domain.matching import normalize_ocr_text, normalize_percent, normalize_text
from imagetocash.domain.models import Address, Debtor, LineItem, OrderDocument
from imagetocash.domain.pricing import amounts_match, line_net_price
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import ParseError, parse_amount
from imagetocash.workflow.protocols import Row

WITH_VAT = "with vat"  # spec 1.7: the VAT setting stays 'With VAT'


def ui_amount(text: str, spec_step: str, what: str) -> Decimal:
    try:
        return parse_amount(text)
    except ParseError as error:
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"{what}: unreadable {text!r}") from error


def check_amount(expected: Decimal, shown: str, spec_step: str, what: str) -> None:
    observed = ui_amount(shown, spec_step, what)
    if not amounts_match(expected, observed):
        raise ManualReviewRequired(
            spec_step, ReviewReason.VALUE_MISMATCH, f"{what}: expected {expected}, screen shows {shown!r}"
        )


def address_lines_missing(address_text: str, expected: Address) -> list[str]:
    """Which parts of `expected` are not visible in an address block read from the UI.

    Fakturama prints the country by name on a line of its own ('...\\r\\nDE-10117 Berlin\\r\\nGermany'),
    so the country must equal a WHOLE line: a substring test would accept 'Niger' inside 'Nigeria'.
    Found live: a wrong country (Georgia for Germany) was saved while street, ZIP and city matched."""
    haystack = normalize_ocr_text(address_text)
    parts = {"street": expected.street, "zip": expected.zip_code, "city": expected.city}
    missing = [label for label, value in parts.items() if normalize_ocr_text(value) not in haystack]
    lines = {normalize_ocr_text(line) for line in address_text.splitlines()}
    if expected.country and normalize_ocr_text(expected.country) not in lines:
        missing.append("country")
    return missing


def check_address(address_text: str, expected: Address, spec_step: str, role: str) -> None:
    missing = address_lines_missing(address_text, expected)
    if missing:
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.VALUE_MISMATCH,
            f"{role} address on screen {address_text!r} lacks {', '.join(missing)} of {expected}",
        )


def check_item_line(row: Row, item: LineItem, spec_step: str) -> None:
    """3.14-3.16 / 4.1: one Items row against its source line."""
    if normalize_ocr_text(row.get("sku", "")) != normalize_ocr_text(item.sku):
        raise ManualReviewRequired(
            spec_step, ReviewReason.VALUE_MISMATCH, f"line {item.position}: SKU {row.get('sku')!r} != {item.sku}"
        )
    check_amount(item.quantity, row.get("quantity", ""), spec_step, f"{item.sku} Qty.")
    check_amount(item.unit_net_price, row.get("unit_price", ""), spec_step, f"{item.sku} U.Price")
    if normalize_percent(row.get("vat", "")) != normalize_percent(str(item.vat_percent)):
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.VALUE_MISMATCH,
            f"{item.sku} VAT shows {row.get('vat')!r}, wanted {item.vat_percent}%",
        )
    check_amount(item.discount_percent, row.get("discount", "0"), spec_step, f"{item.sku} Discount")
    expected_price = line_net_price(item.quantity, item.unit_net_price, item.discount_percent)
    check_amount(expected_price, row.get("price", ""), spec_step, f"{item.sku} line Price")


@dataclass(frozen=True)
class ExistingBooking:
    """The Order and Invoice an earlier run (or a person) already booked for this order."""

    order_number: str
    invoice_number: str


def classify_existing(rows: Sequence[Row], order: OrderDocument, spec_step: str) -> ExistingBooking | None:
    """Duplicate guard (added to the spec, read-only): what does Fakturama already hold for this
    External Reference?

    - nothing -> None: book it (1.3-5.7).
    - exactly one Order and one Invoice that match the image (total, customer, states) ->
      ExistingBooking: already processed, change nothing.
    - anything else (Order without Invoice, two Orders, another total or customer) -> manual
      review, change nothing: a person decides, the run never books the order a second time.
    The Documents search is a substring match over all columns, so rows are filtered here on the
    exact Cust.Ref."""
    wanted = normalize_ocr_text(order.external_reference)
    same = [r for r in rows if normalize_ocr_text(r.get("reference", "")) == wanted]
    if not same:
        return None
    orders = [r for r in same if normalize_text(r.get("type", "")) == "order"]
    invoices = [r for r in same if normalize_text(r.get("type", "")) == "invoice"]
    others = len(same) - len(orders) - len(invoices)
    if len(orders) != 1 or len(invoices) > 1 or others:
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.CONFLICTING_MATCH,
            f"Cust.Ref. already used by {len(orders)} Order(s), {len(invoices)} Invoice(s), {others} other document(s)",
        )
    if not invoices:
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.ALREADY_BOOKED_PARTIAL,
            f"Order {orders[0].get('number')!r} has no Invoice",
        )
    order_row, invoice_row = orders[0], invoices[0]
    for kind, row in (("Order", order_row), ("Invoice", invoice_row)):
        _check_existing_row(row, order, kind, spec_step)
    _check_state(order_row, "open", "Order", spec_step)
    _check_state(invoice_row, "paid" if order.payment.is_paid else "open", "Invoice", spec_step)
    return ExistingBooking(order_row.get("number", ""), invoice_row.get("number", ""))


def _check_existing_row(row: Row, order: OrderDocument, kind: str, spec_step: str) -> None:
    try:
        total = parse_amount(row.get("total", ""))
    except ParseError:
        total = None
    if total is None or not amounts_match(order.totals.gross, total):
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.CONFLICTING_MATCH,
            f"{kind} total {row.get('total')!r} != {order.totals.gross}",
        )
    customer = row.get("customer")
    company = order.debtor.company or order.debtor.search_text
    if customer is not None and normalize_ocr_text(company) not in normalize_ocr_text(customer):
        raise ManualReviewRequired(
            spec_step, ReviewReason.CONFLICTING_MATCH, f"existing {kind} customer {customer!r} is not {company!r}"
        )


def _check_state(row: Row, expected: str, kind: str, spec_step: str) -> None:
    state = normalize_text(row.get("state", ""))
    if state and state != expected:
        reason = ReviewReason.ALREADY_BOOKED_PARTIAL if kind == "Invoice" else ReviewReason.CONFLICTING_MATCH
        raise ManualReviewRequired(spec_step, reason, f"existing {kind} is {state!r}, expected {expected!r}")


def check_order_addresses(shown: Mapping[str, str], debtor: Debtor, spec_step: str) -> None:
    """2.4 / 2.13 / 4.1 / 5.1: the document's Invoice and Delivery address blocks match the image (a
    document without a separate Delivery tab shows one block for both roles)."""
    check_address(shown.get("invoice", ""), debtor.billing_address, spec_step, "Invoice")
    check_address(shown.get("delivery", shown.get("invoice", "")), debtor.delivery_address, spec_step, "Delivery")


def exactly_one_option(offered: Sequence[str], wanted: str, spec_step: str) -> str:
    """2.10 / 5.2: the dropdown offers the extracted payment method exactly once; returns its text."""
    matches = [o for o in offered if normalize_text(o) == normalize_text(wanted)]
    if len(matches) != 1:
        raise ManualReviewRequired(
            spec_step, ReviewReason.PAYMENT_METHOD_UNAVAILABLE, f"{wanted!r} offered {len(matches)}x"
        )
    return matches[0]


def single_row(rows: Sequence[Row], kind: str, number: str, spec_step: str) -> Row:
    """4.5 / 5.5: exactly one Documents row of `kind` carrying the generated document `number`."""
    matches = [
        r
        for r in rows
        if normalize_ocr_text(r.get("number", "")) == normalize_ocr_text(number)
        and (not r.get("type") or normalize_text(r.get("type", "")) == normalize_text(kind))
    ]
    if len(matches) != 1:
        raise ManualReviewRequired(
            spec_step, ReviewReason.VALUE_MISMATCH, f"{len(matches)} {kind} rows numbered {number!r} in Documents"
        )
    return matches[0]


def check_order_row(row: Row, order: OrderDocument, order_number: str, spec_step: str) -> None:
    """4.5 / 5.5: the saved Order's Documents row: number, date, Cust.Ref., state open, total."""
    expected = {"number": order_number, "date": order.order_date.isoformat(), "reference": order.external_reference}
    for field, value in expected.items():
        if field in row and normalize_ocr_text(row[field]) != normalize_ocr_text(value):
            raise ManualReviewRequired(
                spec_step, ReviewReason.VALUE_MISMATCH, f"Order row {field}: {row[field]!r} != {value!r}"
            )
    if "state" in row and "open" not in normalize_text(row["state"]):
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"Order state is {row['state']!r}")
    check_amount(order.totals.gross, row.get("total", "") or str(Decimal(0)), spec_step, "Order row Total")
