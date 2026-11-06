"""Stage 5 (spec 5.1-5.7): check the linked Invoice, apply the payment status, save, verify, stop."""

from __future__ import annotations

from collections.abc import Mapping

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import (
    WITH_VAT,
    check_amount,
    check_item_line,
    check_order_addresses,
    check_order_row,
    exactly_one_option,
    single_row,
)
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi


class InvoiceStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui

    def run(self, ctx: RunContext) -> None:
        ev, invoice, payment = ctx.evidence, self._ui.invoice, ctx.order.payment

        with ev.spec_step("5.1", "Leave No./dates; values were copied from the Order") as rec:
            rec.observed = self._check_copied_values(ctx)

        with ev.spec_step("5.2", "Invoice payment method = extracted method", expected=payment.method):
            invoice.select_payment_method(exactly_one_option(invoice.payment_methods_offered(), payment.method, "5.2"))

        expected = f"paid on {payment.payment_date}, value {ctx.order.totals.gross}" if payment.is_paid else "not paid"
        with ev.spec_step("5.3", f"Paid Status {payment.paid_status}", expected=expected) as rec:
            if payment.is_paid:
                assert payment.payment_date is not None  # guaranteed by validation (1.1)
                invoice.mark_paid(payment.payment_date, ctx.order.totals.gross)
            state = invoice.read_payment_state()
            rec.observed = str(state)
            check_payment_state(state, ctx, "5.3")

        with ev.spec_step("5.4", "Click the toolbar Save once"):
            invoice.save()

        # 5.5 / 5.6: the Documents list is read from the database, so its State column is the proof
        # that the payment status was PERSISTED (the open editor would only show what was typed).
        with ev.spec_step("5.5", "Data > Documents: Invoice state/Total; Order still open") as rec:
            rec.observed = self._check_documents(ctx)

        with ev.spec_step("5.7", "End: no Delivery, Correction or Dunning document"):
            pass

    def _check_copied_values(self, ctx: RunContext) -> str:
        """5.1: reference, VAT mode, order date, addresses, lines and totals came over from the Order."""
        order, invoice = ctx.order, self._ui.invoice
        copied = invoice.read_copied_values()
        ctx.invoice_number = copied.get("number", "")
        if normalize_text(copied.get("reference", "")) != normalize_text(order.external_reference):
            raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"Cust.Ref. {copied.get('reference')!r}")
        if normalize_text(copied.get("vat_mode", WITH_VAT)) != WITH_VAT:
            raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"VAT mode {copied.get('vat_mode')!r}")
        if "order_date" in copied and copied["order_date"] != order.order_date.isoformat():
            raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"Order Date {copied['order_date']!r}")
        check_order_addresses(invoice.read_address_texts(), order.debtor, "5.1")
        lines = invoice.read_item_lines()
        if len(lines) != len(order.items):
            raise ManualReviewRequired("5.1", ReviewReason.VALUE_MISMATCH, f"{len(lines)} Invoice lines")
        for row, item in zip(lines, order.items, strict=True):
            check_item_line(row, item, "5.1")
        check_amount(order.totals.net, copied.get("net", ""), "5.1", "Invoice Total Net")
        check_amount(order.totals.gross, copied.get("total", ""), "5.1", "Invoice Total")
        return str(copied)

    def _check_documents(self, ctx: RunContext) -> str:
        """5.5: one Invoice row (total, state) and the source Order still open. Returns the Invoice
        state as the list shows it; an unreadable state stops the run (persistence unproven)."""
        order, documents = ctx.order, self._ui.documents
        documents.open()
        rows = documents.rows_for_reference(order.external_reference)
        invoice_row = single_row(rows, "invoice", ctx.invoice_number, "5.5")
        check_order_row(single_row(rows, "order", ctx.order_number, "5.5"), order, ctx.order_number, "5.5")
        check_amount(order.totals.gross, invoice_row.get("total", ""), "5.5", "Invoice row Total")
        state = normalize_text(invoice_row.get("state", ""))
        expected = "paid" if order.payment.is_paid else "open"
        if not state:
            raise ManualReviewRequired(
                "5.6", ReviewReason.VALUE_MISMATCH, "Invoice State not readable in Documents: payment status unproven"
            )
        if state != expected:
            raise ManualReviewRequired("5.5", ReviewReason.VALUE_MISMATCH, f"Invoice state {state!r}")
        return state


def check_payment_state(state: Mapping[str, str], ctx: RunContext, spec_step: str) -> None:
    """Paid flag as extracted; when paid, the extracted payment date and the full Invoice total."""
    payment, total = ctx.order.payment, ctx.order.totals.gross
    is_paid = normalize_text(state.get("paid", "")) in {"true", "yes", "paid", "1"}
    if is_paid != payment.is_paid:
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"paid flag is {state.get('paid')!r}")
    if payment.is_paid:
        if state.get("date") != (payment.payment_date.isoformat() if payment.payment_date else None):
            raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"payment date {state.get('date')!r}")
        check_amount(total, state.get("value", ""), spec_step, "paid Value")
