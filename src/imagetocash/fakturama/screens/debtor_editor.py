"""New Debtor editor (spec 2.5-2.11). Labels come from the spec; confirm them with `imagetocash inspect`."""

from __future__ import annotations

from typing import Any

from imagetocash.automation.input import read_value, select_combo_option, set_and_verify, set_checkbox
from imagetocash.domain.models import Debtor
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext

S = "debtor_editor"


class DebtorEditorScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._title = ""

    def open_new_debtor(self) -> None:
        """2.5: the Order tab stays open; New Contact in the left New panel opens a new editor tab."""
        self._ctx.session.bring_to_front()
        before = self._ctx.tab_titles()
        self._ctx.find("main", "new_contact").click_input()  # navigation entry: no Invoke pattern
        self._title = self._ctx.wait_for_new_tab(before)

    def activate(self) -> None:
        self._ctx.activate_tab(self._title)

    def fill_identity(self, debtor: Debtor) -> None:
        # 2.6: Customer ID and Salutation are deliberately not touched.
        self._set("company", debtor.company, "2.6", "Company")
        self._set("first_name", debtor.first_name, "2.6", "First Name")
        self._set("last_name", debtor.last_name, "2.6", "Last Name")

    def fill_main_address(self, debtor: Debtor) -> None:
        self._open_tab("main_address_tab")
        a = debtor.billing_address
        self._set("street", a.street, "2.7", "Street")
        self._set("zip", a.zip_code, "2.7", "ZIP")
        self._set("city", a.city, "2.7", "City")
        select_combo_option(self._field("country"), a.country, spec_step="2.7", field_name="Country")
        self._set("email", debtor.email, "2.7", "E-Mail")
        self._set("telephone", debtor.telephone, "2.7", "Telephone")

    def assign_address_roles(self, debtor: Debtor) -> None:
        set_checkbox(self._field("invoice_role"), True, spec_step="2.8", field_name="Invoice address role")
        if debtor.billing_equals_delivery:
            set_checkbox(self._field("delivery_role"), True, spec_step="2.8", field_name="Delivery address role")
            return
        # The spec shows only the identical-address case; the sample order has a separate delivery
        # address, whose UI (add a second address + Delivery role) still has to be mapped live.
        raise ManualReviewRequired(
            "2.8",
            ReviewReason.NOT_IMPLEMENTED,
            "separate Delivery address: second-address UI not mapped yet (see README 'Not done')",
        )

    def fill_miscellaneous(self, debtor: Debtor) -> None:
        self._open_tab("miscellaneous_tab")
        self._set("alias", debtor.alias, "2.9", "Alias name")
        discount = self._field("discount")
        if read_value(discount).strip() not in {"0", "0%", "0.00 %", "0,00 %"}:
            set_and_verify(discount, "0", spec_step="2.9", field_name="Discount")
        select_combo_option(self._field("net_or_gross"), "Net", spec_step="2.9", field_name="Net or Gross")

    def payment_methods_offered(self) -> list[str]:
        self._open_tab("payment_tab")
        combo = self._field("payment_method")
        combo.expand()
        try:
            return [str(item.element_info.name) for item in combo.descendants(control_type="ListItem")]
        finally:
            combo.collapse()

    def select_payment_method(self, name: str) -> None:
        self._open_tab("payment_tab")
        select_combo_option(self._field("payment_method"), name, spec_step="2.10", field_name="Payment Method")

    def save(self) -> None:
        self._ctx.save_via_toolbar(self._title)

    # --- helpers -----------------------------------------------------------------------------
    def _pane(self) -> Any:
        return self._ctx.content_pane(self._title)

    def _field(self, key: str) -> Any:
        return self._ctx.find(S, key, scope=self._pane())

    def _set(self, key: str, value: str, spec_step: str, name: str) -> None:
        if value:
            set_and_verify(self._field(key), value, spec_step=spec_step, field_name=name)

    def _open_tab(self, key: str) -> None:
        tab_name = str(self._ctx.selectors.value(S, key))
        item = next(
            (t for t in self._pane().descendants(control_type="TabItem") if t.element_info.name == tab_name), None
        )
        if item is None:
            raise ManualReviewRequired("2.7", ReviewReason.UI_ELEMENT_NOT_FOUND, f"Debtor tab {tab_name!r} not found")
        item.iface_selection_item.Select()
