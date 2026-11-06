"""The linked Invoice editor opened by the Order's follow-up action (spec 4.7, 5.1-5.6). It shares the
Order editor's layout for addresses, items and totals, plus a payment row (paid / method / at / Value)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from imagetocash.automation.date_input import set_cdatetime
from imagetocash.automation.input import combo_options, read_value, select_combo_option, set_and_verify, set_checkbox
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.base_editor import EditorScreen
from imagetocash.fakturama.screens.order_editor import OrderEditorScreen
from imagetocash.fakturama.values import iso_date, money_text


class InvoiceEditorScreen(EditorScreen):
    section = "invoice_editor"
    opened_at = "4.7"

    def __init__(self, ctx: ScreenContext, order: OrderEditorScreen) -> None:
        super().__init__(ctx)
        self._order = order
        self._payment_options: list[str] = []

    def wait_until_open(self) -> None:
        """4.7: the linked Invoice opens as a new editor tab after the Order's follow-up action."""
        self._tab = self._ctx.workbench.wait_for_new(self._order.tabs_before_follow_up)

    def read_copied_values(self) -> dict[str, str]:
        totals = self._as_order_view().read_totals()
        return {
            "number": read_value(self._field("number")),
            "reference": read_value(self._field("customer_reference")),
            "order_date": iso_date(read_value(self._field("order_date")), self._ctx.ui_date_parse_format),
            "vat_mode": read_value(self._field("vat_mode")),
            "net": totals["net"],
            "total": totals["total"],
        }

    def read_address_texts(self) -> dict[str, str]:
        return self._as_order_view().read_address_texts()

    def read_item_lines(self) -> list[dict[str, str]]:
        return self._as_order_view().read_item_lines()

    def payment_methods_offered(self) -> list[str]:
        self._payment_options = combo_options(self._field("payment_method"))
        return [o.strip() for o in self._payment_options]

    def select_payment_method(self, name: str) -> None:
        select_combo_option(
            self._field("payment_method"),
            name,
            spec_step="5.2",
            field_name="payment method",
            options=self._payment_options or None,
        )

    def mark_paid(self, payment_date: date, value: Decimal) -> None:
        set_checkbox(self._field("paid"), True, spec_step="5.3", field_name="paid")
        self._ctx.invalidate()  # the 'at' date and Value fields appear once 'paid' is ticked
        set_cdatetime(
            self._field("payment_date"),
            payment_date,
            enter_from=self._field("payment_method"),  # the date follows the method combo
            parse_format=self._ctx.ui_date_parse_format,
            commit=self._field("paid_value").set_focus,
            spec_step="5.3",
            field_name="payment date",
        )
        set_and_verify(
            self._field("paid_value"), f"{value:.2f}", spec_step="5.3", field_name="Value", normalize=money_text
        )

    def read_payment_state(self) -> dict[str, str]:
        paid = bool(self._field("paid").iface_toggle.CurrentToggleState)
        state = {"paid": "true" if paid else "false"}
        if paid:
            state["date"] = iso_date(read_value(self._field("payment_date")), self._ctx.ui_date_parse_format)
            state["value"] = read_value(self._field("paid_value"))
        return state

    def _as_order_view(self) -> OrderEditorScreen:
        return OrderEditorScreen.for_existing_tab(self._ctx, self.tab)
