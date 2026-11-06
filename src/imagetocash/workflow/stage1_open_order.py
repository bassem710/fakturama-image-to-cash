"""Stage 1 (spec 1.3-1.8): open a New Order and fill its header. Spec 1.1-1.2 run in runner.py."""

from __future__ import annotations

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import WITH_VAT
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi


class OpenOrderStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui

    def run(self, ctx: RunContext) -> None:
        order_ui, order, ev = self._ui.order, ctx.order, ctx.evidence

        with ev.spec_step("1.3", "Click toolbar Order, wait for the New Order editor"):
            order_ui.open_new_order()

        with ev.spec_step("1.4", "Leave the proposed No. unchanged") as rec:
            ctx.order_number = order_ui.read_document_number()
            rec.observed = ctx.order_number
            if not ctx.order_number.strip():
                raise ManualReviewRequired("1.4", ReviewReason.VALUE_MISMATCH, "no document number proposed")

        with ev.spec_step("1.5", "Set Date to the Order Date", expected=order.order_date.isoformat()):
            order_ui.set_order_date(order.order_date)

        with ev.spec_step("1.6", "Enter External Reference in Cust.Ref.", expected=order.external_reference):
            order_ui.set_customer_reference(order.external_reference)

        with ev.spec_step("1.7", "Price mode Net, VAT stays With VAT", expected="Net / With VAT") as rec:
            order_ui.set_price_mode_net()
            vat_mode = order_ui.read_vat_mode()
            rec.observed = vat_mode
            if normalize_text(vat_mode) != WITH_VAT:
                raise ManualReviewRequired("1.7", ReviewReason.VALUE_MISMATCH, f"VAT mode is {vat_mode!r}")

        with ev.spec_step("1.8", "Keep this New Order tab open for the rest of the flow"):
            order_ui.activate()
