"""New Debtor editor (spec 2.5-2.11), mapped live: identity fields on top, an 'Addresses' tab folder
(Main address + '+' for additional addresses, each with an 'address type' role popup) and a
'Miscellaneous' tab with Alias name, Discount, Net or Gross and the Payment combo."""

from __future__ import annotations

from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import (
    combo_options,
    read_value,
    select_combo_option,
    select_tab_item,
    set_and_verify,
    set_checkbox,
)
from imagetocash.automation.locators import ByProperties, locate
from imagetocash.automation.waiting import wait_until
from imagetocash.domain.matching import normalize_text
from imagetocash.domain.models import Address, Debtor
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import EditorTab, ScreenContext

S = "debtor_editor"


class DebtorEditorScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._tab: EditorTab | None = None

    def open_new_debtor(self) -> None:
        """2.5: the Order tab stays open; New Contact in the left New panel opens 'New Debtor'."""
        self._ctx.session.bring_to_front()
        before = self._ctx.tab_snapshot()
        self._ctx.find("main", "new_contact").click_input()  # navigation entry: no Invoke pattern
        self._tab = self._ctx.wait_for_new_tab(before)

    def activate(self) -> None:
        self._ctx.activate_editor(self._require_tab())

    def fill_identity(self, debtor: Debtor) -> None:
        # 2.6: Customer ID and Salutation ('---') are deliberately not touched.
        self._set("company", debtor.company, "2.6", "Company")
        self._set("first_name", debtor.first_name, "2.6", "First Name")
        self._set("last_name", debtor.last_name, "2.6", "Last Name")

    def fill_main_address(self, debtor: Debtor) -> None:
        """2.7: Main address = billing address, plus E-Mail and Telephone."""
        tab = self._address_tab("main_address_tab")
        self._fill_address(tab, debtor.billing_address, company=debtor.company, spec_step="2.7")
        self._set("email", debtor.email, "2.7", "E-Mail", scope=tab)
        self._set("telephone", debtor.telephone, "2.7", "Telephone", scope=tab)

    def assign_address_roles(self, debtor: Debtor) -> None:
        """2.8: Main address gets the Invoice role; identical delivery -> also Delivery role, no new
        address. A different delivery address (the sample order) becomes an additional address with
        the Delivery role."""
        main_tab = self._address_tab("main_address_tab")
        self._set_roles(main_tab, invoice=True, delivery=debtor.billing_equals_delivery)
        if debtor.billing_equals_delivery:
            return
        self._ctx.press(self._ctx.find(S, "add_address", scope=main_tab))
        extra = self._address_tab("additional_address_tab")
        self._fill_address(extra, debtor.delivery_address, company=debtor.company, spec_step="2.8")
        self._set_roles(extra, invoice=False, delivery=True)

    def fill_miscellaneous(self, debtor: Debtor) -> None:
        self._open_inner_tab("miscellaneous_tab")
        self._set("alias", debtor.alias, "2.9", "Alias name")
        discount = self._field("discount")
        if read_value(discount).strip() not in {"0", "0%", "0.00%", "0.00 %"}:
            set_and_verify(discount, "0", spec_step="2.9", field_name="Discount", normalize=_digits)
        select_combo_option(self._field("net_or_gross"), "Net", spec_step="2.9", field_name="Net or Gross")

    def payment_methods_offered(self) -> list[str]:
        self._open_inner_tab("miscellaneous_tab")
        return [o.strip() for o in combo_options(self._field("payment_method"))]

    def select_payment_method(self, name: str) -> None:
        self._open_inner_tab("miscellaneous_tab")
        select_combo_option(self._field("payment_method"), name, spec_step="2.10", field_name="Payment")

    def save(self) -> None:
        self._ctx.save_editor(self._require_tab())

    # --- helpers --------------------------------------------------------------------------------
    def _pane(self) -> Any:
        return self._ctx.editor_pane(self._require_tab())

    def _require_tab(self) -> EditorTab:
        if self._tab is None:
            raise ManualReviewRequired("2.5", ReviewReason.UI_ELEMENT_NOT_FOUND, "no Debtor editor opened")
        return self._tab

    def _field(self, key: str, scope: Any | None = None) -> Any:
        return self._ctx.find(S, key, scope=scope if scope is not None else self._pane())

    def _set(self, key: str, value: str, spec_step: str, name: str, scope: Any | None = None) -> None:
        if value:  # never invent: empty source values leave the field at its default
            set_and_verify(self._field(key, scope), value, spec_step=spec_step, field_name=name)

    def _open_inner_tab(self, key: str) -> Any:
        title = str(self._ctx.selectors.value(S, key))
        item = wait_until(
            lambda: next(
                (t for t in self._pane().descendants(control_type="TabItem") if t.element_info.name == title), None
            ),
            timeout=self._ctx.settings.timeouts.element,
            what=f"Debtor tab '{title}'",
        )
        select_tab_item(item)
        return wait_until(
            lambda: next(
                (f for f in self._pane().descendants(control_type="Tab") if f.element_info.name == title), None
            ),
            timeout=self._ctx.settings.timeouts.element,
            what=f"Debtor tab '{title}' content",
        )

    def _address_tab(self, key: str) -> Any:
        self._open_inner_tab("addresses_tab")
        return self._open_inner_tab(key)

    def _fill_address(self, tab: Any, address: Address, *, company: str, spec_step: str) -> None:
        # 'additional name' only when the address carries a name other than the Debtor's company.
        if address.name and normalize_text(address.name) != normalize_text(company):
            self._set("additional_name", address.name, spec_step, "additional name", scope=tab)
        self._set("street", address.street, spec_step, "Street", scope=tab)
        self._set("zip", address.zip_code, spec_step, "ZIP", scope=tab)
        self._set("city", address.city, spec_step, "City", scope=tab)
        select_combo_option(self._field("country", tab), address.country, spec_step=spec_step, field_name="Country")

    def _set_roles(self, tab: Any, *, invoice: bool, delivery: bool) -> None:
        """The button after 'address type' opens a popup (a child pane of the main window) with the
        role checkboxes."""
        label = str(self._ctx.selectors.value(S, "address_type_label"))
        siblings = list(locate(tab, ByProperties(control_type="Text", name=label)).parent().children())
        index = next(i for i, e in enumerate(siblings) if e.element_info.name == label)
        button = next(iter(siblings[index + 1].descendants(control_type="Button")), None)
        if button is None:
            raise ManualReviewRequired("2.8", ReviewReason.UI_ELEMENT_NOT_FOUND, "address type button not found")
        button.click_input()
        main = self._ctx.main()
        set_checkbox(self._ctx.find(S, "invoice_role", scope=main), invoice, spec_step="2.8", field_name="Invoice role")
        set_checkbox(
            self._ctx.find(S, "delivery_role", scope=main), delivery, spec_step="2.8", field_name="Delivery role"
        )
        keyboard.send_keys("{ESC}")  # close the role popup


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit() or ch == ".").rstrip("0").rstrip(".") or "0"
