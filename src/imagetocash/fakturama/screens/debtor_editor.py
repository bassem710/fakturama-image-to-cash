"""New Debtor editor (spec 2.5-2.11): identity fields on top, an 'Addresses' tab folder (Main address +
'+' for additional addresses, each with an 'address type' role popup) and a 'Miscellaneous' tab with
Alias name, Discount, Net or Gross and the Payment combo."""

from __future__ import annotations

from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import (
    combo_options,
    is_selected,
    read_value,
    select_combo_option,
    select_tab_item,
    set_and_verify,
)
from imagetocash.automation.locators import ByProperties, find_first, locate
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.matching import normalize_text
from imagetocash.domain.models import Address, Debtor
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.base_editor import EditorScreen
from imagetocash.fakturama.values import is_zero, number_text


class DebtorEditorScreen(EditorScreen):
    section = "debtor_editor"
    opened_at = "2.5"

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx)
        self._payment_options: list[str] = []

    def open_new_debtor(self) -> None:
        """2.5: the Order tab stays open; New Contact in the left New panel opens 'New Debtor'."""
        self._tab = self._ctx.workbench.open_new("new_contact", "new_contact_toolbar")

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
        address. A different delivery address becomes an additional address with the Delivery role."""
        main_tab = self._address_tab("main_address_tab")
        self._set_roles(main_tab, invoice=True, delivery=debtor.billing_equals_delivery)
        if debtor.billing_equals_delivery:
            return
        self._ctx.press(self._field("add_address", main_tab))
        extra = self._address_tab("additional_address_tab")
        self._fill_address(extra, debtor.delivery_address, company=debtor.company, spec_step="2.8")
        self._set_roles(extra, invoice=False, delivery=True)

    def fill_miscellaneous(self, debtor: Debtor) -> None:
        self._open_inner_tab("miscellaneous_tab")
        self._set("alias", debtor.alias, "2.9", "Alias name")
        discount = self._field("discount")
        if not is_zero(read_value(discount)):
            set_and_verify(discount, "0", spec_step="2.9", field_name="Discount", normalize=number_text)
        select_combo_option(
            self._field("net_or_gross"), self._word("net_option"), spec_step="2.9", field_name="Net or Gross"
        )

    def payment_methods_offered(self) -> list[str]:
        self._open_inner_tab("miscellaneous_tab")
        self._payment_options = combo_options(self._field("payment_method"))
        return [o.strip() for o in self._payment_options]

    def select_payment_method(self, name: str) -> None:
        self._open_inner_tab("miscellaneous_tab")
        select_combo_option(
            self._field("payment_method"),
            name,
            spec_step="2.10",
            field_name="Payment",
            options=self._payment_options or None,
        )

    # --- helpers --------------------------------------------------------------------------------
    def _set(self, key: str, value: str, spec_step: str, name: str, scope: Any | None = None) -> None:
        if value:  # never invent: empty source values leave the field at its default
            set_and_verify(self._field(key, scope), value, spec_step=spec_step, field_name=name)

    def _open_inner_tab(self, key: str) -> Any:
        """Select the editor's inner tab `key` (no-op when it already is) and return its content folder
        (a tab folder's UIA name is the title of its selected tab)."""
        title = self._word(key)
        pane = self._pane()
        item = wait_until(
            lambda: find_first(pane, control_type="TabItem", name=title),
            timeout=self._ctx.settings.timeouts.element,
            what=f"Debtor tab '{title}'",
        )
        if not is_selected(item):
            select_tab_item(item)
            self._ctx.invalidate()
        return wait_until(
            lambda: find_first(pane, control_type="Tab", name=title),
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
        """Roles live in a popup opened by the button after 'address type'. The popup checkboxes'
        Toggle state reads stale over UIA, so each wanted change is toggled ONCE and the read-back is
        the 'address type' text field next to the button, which always shows the assigned roles."""
        label = self._word("address_type_label")
        siblings = list(locate(tab, ByProperties(control_type="Text", name=label)).parent().children())
        index = next(i for i, e in enumerate(siblings) if e.element_info.name == label)
        role_text = find_first(siblings[index + 1], control_type="Edit")
        button = find_first(siblings[index + 1], control_type="Button")
        if role_text is None or button is None:
            raise ManualReviewRequired("2.8", ReviewReason.UI_ELEMENT_NOT_FOUND, "address type field not found")

        wanted = {"invoice_role": invoice, "delivery_role": delivery}

        def role_shown(key: str) -> bool:
            role_name = str(self._ctx.selectors.value(self.section, key)["name"])
            return normalize_text(role_name) in normalize_text(read_value(role_text))

        to_flip = [key for key, on in wanted.items() if role_shown(key) != on]
        if to_flip:
            self._ctx.press(button)  # Invoke opens the popup (a separate window: searched live)
            for key in to_flip:
                checkbox = self._ctx.find(self.section, key)
                try:
                    checkbox.iface_toggle.Toggle()
                except Exception:
                    checkbox.click_input()  # element click fallback
            keyboard.send_keys("{ESC}")  # close the role popup
        try:
            wait_until(
                lambda: all(role_shown(key) == on for key, on in wanted.items()),
                timeout=self._ctx.settings.timeouts.element,
                what="address roles",
            )
        except WaitTimeout as error:
            raise ManualReviewRequired(
                "2.8", ReviewReason.VALUE_MISMATCH, f"address type shows {read_value(role_text)!r}, wanted {wanted}"
            ) from error
