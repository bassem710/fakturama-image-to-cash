"""Stage 4 (spec 4.1-4.7): check and save the Order, then open its linked Invoice."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from imagetocash.domain.matching import normalize_ocr_text, normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import check_address, check_amount, check_item_line
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi, Row


def single_row(rows: Sequence[Row], kind: str, number: str, spec_step: str) -> Row:
    """Exactly one Documents row of `kind` carrying the generated document `number`."""
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


class SaveOrderStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui

    def run(self, ctx: RunContext) -> None:
        order, ev, order_ui = ctx.order, ctx.evidence, self._ui.order

        with ev.spec_step("4.1", "Debtor addresses and every line match the image"):
            order_ui.activate()
            shown = order_ui.read_address_texts()
            check_address(shown.get("invoice", ""), order.debtor.billing_address, "4.1", "Invoice")
            check_address(
                shown.get("delivery", shown.get("invoice", "")), order.debtor.delivery_address, "4.1", "Delivery"
            )
            lines = order_ui.read_item_lines()
            for row, item in zip(lines, order.items, strict=False):
                check_item_line(row, item, "4.1")

        with ev.spec_step("4.2", "Discount 0%, Shipping free / 0.00 unless the image says otherwise"):
            if order.order_discount_percent or order.shipping_net:
                raise ManualReviewRequired(
                    "4.2", ReviewReason.NOT_IMPLEMENTED, "order-level discount/shipping on the image is not automated"
                )
            order_ui.ensure_order_level_defaults()

        with ev.spec_step("4.3", "Total Net, VAT, Total match the source", expected=str(order.totals)) as rec:
            totals = order_ui.read_totals()
            rec.observed = str(totals)
            check_amount(order.totals.net, totals.get("net", ""), "4.3", "Total Net")
            check_amount(order.totals.vat, totals.get("vat", ""), "4.3", "VAT")
            check_amount(order.totals.gross, totals.get("total", ""), "4.3", "Total")

        with ev.spec_step("4.4", "Click the toolbar Save once"):
            order_ui.save()

        with ev.spec_step("4.5", "Data > Documents: one open Order row with the generated number") as rec:
            self._ui.documents.open()
            rows = self._ui.documents.rows_for_reference(order.external_reference)
            row = single_row(rows, "order", ctx.order_number, "4.5")
            rec.observed = str(row)
            check_order_row(row, ctx, "4.5")

        with ev.spec_step("4.6", "Create a follow-up document > Invoice (not the toolbar)"):
            order_ui.create_follow_up_invoice()

        with ev.spec_step("4.7", "Wait for the linked New Invoice editor"):
            self._ui.invoice.wait_until_open()


def check_order_row(row: Row, ctx: RunContext, spec_step: str) -> None:
    order = ctx.order
    expected = {
        "number": ctx.order_number,
        "date": order.order_date.isoformat(),
        "reference": order.external_reference,
    }
    for field, value in expected.items():
        if field in row and normalize_ocr_text(row[field]) != normalize_ocr_text(value):
            raise ManualReviewRequired(
                spec_step, ReviewReason.VALUE_MISMATCH, f"Order row {field}: {row[field]!r} != {value!r}"
            )
    if "state" in row and "open" not in normalize_text(row["state"]):
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"Order state is {row['state']!r}")
    check_amount(order.totals.gross, row.get("total", "") or str(Decimal(0)), spec_step, "Order row Total")
