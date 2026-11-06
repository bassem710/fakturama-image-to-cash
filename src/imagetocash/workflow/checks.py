"""On-screen verifications shared by stages 2-5 ("verify each step before moving to the next")."""

from __future__ import annotations

from decimal import Decimal

from imagetocash.domain.matching import normalize_ocr_text, normalize_percent
from imagetocash.domain.models import Address, LineItem
from imagetocash.domain.pricing import amounts_match, line_net_price
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import ParseError, parse_amount
from imagetocash.workflow.protocols import Row, address_lines_missing


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
