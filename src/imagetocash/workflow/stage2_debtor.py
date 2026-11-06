"""Stage 2 (spec 2.1-2.13): select the Debtor from the Order, or create it and select it again."""

from __future__ import annotations

from imagetocash.domain.matching import DEBTOR_MATCH_POLICY, PAYMENT_METHOD_MATCH_POLICY, normalize_text
from imagetocash.domain.payment_codes import payment_code_for
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import check_address
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi
from imagetocash.workflow.resolver import decide, require_exact


class DebtorStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui
        self._policy = DEBTOR_MATCH_POLICY.ocr_tolerant()

    def run(self, ctx: RunContext) -> None:
        debtor, ev, order_ui = ctx.order.debtor, ctx.evidence, self._ui.order
        wanted = debtor.match_record()

        with ev.spec_step("2.1", "Open Select the address (upper icon beside Addresses)"):
            dialog = order_ui.open_address_selector()

        with ev.spec_step("2.2", "Search by company / customer name", expected=debtor.search_text) as rec:
            rows = dialog.search(debtor.search_text)
            rec.observed = f"{len(rows)} row(s)"

        with ev.spec_step("2.3", "Exact match on Company, First Name, Name, ZIP, City") as rec:
            row = decide(self._policy, wanted, rows, "2.3")
            if row is None:
                dialog.cancel()
                rec.observed = "no exact row -> Cancel, create the Debtor"
            else:
                dialog.choose(row)
                rec.observed = "exact row selected -> OK"
                ctx.debtor_row = row

        if row is not None:
            with ev.spec_step("2.4", "Populated Invoice / Delivery address match the image"):
                self._check_order_addresses(ctx, "2.4")
            return

        self._create_debtor(ctx)

        with ev.spec_step("2.12", "Back on the Order: search again, select the new Debtor, OK") as rec:
            order_ui.activate()
            dialog = order_ui.open_address_selector()
            row = require_exact(self._policy, wanted, dialog.search(debtor.search_text), "2.12")
            dialog.choose(row)
            ctx.debtor_row = row
            rec.observed = "new Debtor selected"

        with ev.spec_step("2.13", "Invoice / Delivery address populate correctly"):
            self._check_order_addresses(ctx, "2.13")

    def _create_debtor(self, ctx: RunContext) -> None:
        debtor, ev, debtor_ui = ctx.order.debtor, ctx.evidence, self._ui.debtor
        with ev.spec_step("2.5", "Keep Order open; New Contact in the New panel"):
            debtor_ui.open_new_debtor()
        with ev.spec_step("2.6", "Company, First Name, Last Name; keep Customer ID and Salutation"):
            debtor_ui.fill_identity(debtor)
        with ev.spec_step("2.7", "Main address: Street, ZIP, City, Country, E-Mail, Telephone"):
            debtor_ui.fill_main_address(debtor)
        roles = "Invoice + Delivery" if debtor.billing_equals_delivery else "Invoice (+ separate Delivery address)"
        with ev.spec_step("2.8", "Assign address roles", expected=roles):
            debtor_ui.assign_address_roles(debtor)
        with ev.spec_step("2.9", "Miscellaneous: Alias name, Discount 0%, Net"):
            debtor_ui.fill_miscellaneous(debtor)
        self._resolve_payment_method(ctx)
        with ev.spec_step("2.11", "Save the Debtor once"):
            debtor_ui.save()

    def _resolve_payment_method(self, ctx: RunContext) -> None:
        method, ev = ctx.order.payment.method, ctx.evidence
        debtor_ui, payment_list, editor = self._ui.debtor, self._ui.payment_methods, self._ui.payment_method_editor

        with ev.spec_step("2.10", "Payment tab: select the exact Payment Method", expected=method) as rec:
            offered = [o for o in debtor_ui.payment_methods_offered() if normalize_text(o) == normalize_text(method)]
            if len(offered) > 1:
                raise ManualReviewRequired("2.10", ReviewReason.AMBIGUOUS_MATCH, f"{method!r} offered twice")
            if offered:
                debtor_ui.select_payment_method(offered[0])
                rec.observed = "available -> selected"
                return
            rec.observed = "not available -> create it (2.10.1)"

        policy = PAYMENT_METHOD_MATCH_POLICY.ocr_tolerant()
        with ev.spec_step("2.10.1", "Data > terms of payment: search the exact method") as rec:
            payment_list.open()
            rows = payment_list.search(method)
            rec.observed = f"{len(rows)} row(s)"

        with ev.spec_step("2.10.2", "One exact row -> reuse; none -> green +") as rec:
            existing = decide(policy, {"name": method}, rows, "2.10.2")
            if existing is not None:
                debtor_ui.activate()
                debtor_ui.select_payment_method(method)
                rec.observed = "existing method selected in the Debtor editor"
                return
            payment_code = payment_code_for(method)  # 2.10.4 checked BEFORE anything is created
            payment_list.create_new()
            rec.observed = "none -> new payment method"

        with (
            ev.spec_step("2.10.3", "Name = Description = method; Account blank"),
            ev.spec_step("2.10.4", "Payment code", expected=payment_code),
            ev.spec_step("2.10.5", "Cash discount, Discount Days, Net Days 0; texts blank; not standard"),
        ):
            editor.fill(method, payment_code)

        with ev.spec_step("2.10.6", "Save once, back to the Debtor editor, select the new method"):
            editor.save()
            require_exact(policy, {"name": method}, payment_list.search(method), "2.10.6")
            debtor_ui.activate()
            debtor_ui.select_payment_method(method)

    def _check_order_addresses(self, ctx: RunContext, spec_step: str) -> None:
        debtor = ctx.order.debtor
        shown = self._ui.order.read_address_texts()
        check_address(shown.get("invoice", ""), debtor.billing_address, spec_step, "Invoice")
        check_address(shown.get("delivery", shown.get("invoice", "")), debtor.delivery_address, spec_step, "Delivery")
