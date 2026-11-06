"""Stage 5 (spec 5.1-5.7): check the linked Invoice, apply the payment status, verify, stop."""

from __future__ import annotations

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import check_address, check_amount, check_item_line
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi
from imagetocash.workflow.stage4_save_order import check_order_row, single_row


class InvoiceStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui

    def run(self, ctx: RunContext) -> None:
        order, ev, invoice = ctx.order, ctx.evidence, self._ui.invoice

        with ev.spec_step("5.1", "Leave No./dates; values were copied from the Order") as rec:
            copied = invoice.read_copied_values()
            rec.observed = str(copied)
            ctx.invoice_number = copied.get("number", "")
            if normalize_text(copied.get("reference", "")) != normalize_text(order.external_reference):
                raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"Cust.Ref. {copied.get('reference')!r}")
            if normalize_text(copied.get("vat_mode", "with vat")) != "with vat":
                raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"VAT mode {copied.get('vat_mode')!r}")
            if "order_date" in copied and copied["order_date"] != order.order_date.isoformat():
                raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"Order Date {copied['order_date']!r}")
            shown = invoice.read_address_texts()
            check_address(shown.get("invoice", ""), order.debtor.billing_address, "5.1", "Invoice")
            check_address(
                shown.get("delivery", shown.get("invoice", "")), order.debtor.delivery_address, "5.1", "Delivery"
            )
            lines = invoice.read_item_lines()
            if len(lines) != len(order.items):
                raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"{len(lines)} Invoice lines")
            for row, item in zip(lines, order.items, strict=True):
                check_item_line(row, item, "5.1")
            check_amount(order.totals.net, copied.get("net", ""), "5.1", "Invoice Total Net")
            check_amount(order.totals.gross, copied.get("total", ""), "5.1", "Invoice Total")

        with ev.spec_step("5.2", "Invoice payment method = extracted method", expected=order.payment.method):
            offered = [
                m
                for m in invoice.payment_methods_offered()
                if normalize_text(m) == normalize_text(order.payment.method)
            ]
            if len(offered) != 1:
                raise ManualReviewRequired(
                    "5.2", ReviewReason.PAYMENT_METHOD_UNAVAILABLE, f"{order.payment.method!r} offered {len(offered)}x"
                )
            invoice.select_payment_method(offered[0])

        paid = order.payment.is_paid
        expected_state = (
            f"paid on {order.payment.payment_date}, value {order.totals.gross}" if paid else "not paid, no date/value"
        )
        with ev.spec_step("5.3", f"Paid Status {order.payment.paid_status}", expected=expected_state) as rec:
            if paid:
                assert order.payment.payment_date is not None  # guaranteed by validation (1.1)
                invoice.mark_paid(order.payment.payment_date, order.totals.gross)
            state = invoice.read_payment_state()
            rec.observed = str(state)
            self._check_payment_state(state, ctx, "5.3")

        with ev.spec_step("5.4", "Click the toolbar Save once"):
            invoice.save()

        with ev.spec_step("5.5", "Data > Documents: Invoice state/Total; Order still open") as rec:
            self._ui.documents.open()
            rows = self._ui.documents.rows_for_reference(order.external_reference)
            invoice_row = single_row(rows, "invoice", ctx.invoice_number, "5.5")
            order_row = single_row(rows, "order", ctx.order_number, "5.5")
            rec.observed = f"invoice={invoice_row} order={order_row}"
            check_amount(order.totals.gross, invoice_row.get("total", ""), "5.5", "Invoice row Total")
            check_order_row(order_row, ctx, "5.5")  # the source Order is still open, same Cust.Ref./Total
            invoice_state = normalize_text(invoice_row.get("state", ""))
            expected_state = "paid" if order.payment.is_paid else "open"
            if invoice_state and expected_state not in invoice_state:
                raise ManualReviewRequired("5.5", ReviewReason.VALUE_MISMATCH, f"Invoice state {invoice_state!r}")

        if not invoice_state:
            with ev.spec_step("5.6", "Reopen the Invoice to confirm the persisted payment data") as rec:
                state = invoice.read_payment_state()
                rec.observed = str(state)
                self._check_payment_state(state, ctx, "5.6")

        with ev.spec_step("5.7", "End: no Delivery, Correction or Dunning document"):
            pass

    @staticmethod
    def _check_payment_state(state: dict[str, str], ctx: RunContext, spec_step: str) -> None:
        payment, total = ctx.order.payment, ctx.order.totals.gross
        is_paid = normalize_text(state.get("paid", "")) in {"true", "yes", "paid", "1"}
        if is_paid != payment.is_paid:
            raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"paid flag is {state.get('paid')!r}")
        if payment.is_paid:
            if state.get("date") != (payment.payment_date.isoformat() if payment.payment_date else None):
                raise ManualReviewRequired(
                    spec_step, ReviewReason.VALUE_MISMATCH, f"payment date {state.get('date')!r}"
                )
            check_amount(total, state.get("value", ""), spec_step, "paid Value")
