"""The linked Invoice editor opened by the Order's follow-up action (spec 4.7, 5.1-5.6).
Assumed to mirror the Order editor; confirm with `imagetocash inspect` after 4.6."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from imagetocash.automation.date_input import set_cdatetime
from imagetocash.automation.input import (
    combo_options,
    read_value,
    select_combo_option,
    set_and_verify,
    set_checkbox,
)
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import parse_amount
from imagetocash.fakturama.screen_context import EditorTab, ScreenContext
from imagetocash.fakturama.screens.order_editor import OrderEditorScreen

S = "invoice_editor"


class InvoiceEditorScreen:
    def __init__(self, ctx: ScreenContext, order: OrderEditorScreen) -> None:
        self._ctx, self._order = ctx, order
        self._tab: EditorTab | None = None

    def wait_until_open(self) -> None:
        """4.7: the linked Invoice opens as a new editor tab after the Order's follow-up action."""
        self._tab = self._ctx.wait_for_new_tab(self._order.tabs_before_follow_up)

    def read_copied_values(self) -> dict[str, str]:
        totals = self._totals()
        return {
            "number": read_value(self._field("number")),
            "reference": read_value(self._field("customer_reference")),
            "order_date": self._iso(read_value(self._field("order_date"))),
            "vat_mode": read_value(self._field("vat_mode")),
            "net": totals["net"],
            "total": totals["total"],
        }

    def read_address_texts(self) -> dict[str, str]:
        return self._as_order_view().read_address_texts()

    def read_item_lines(self) -> list[dict[str, str]]:
        return self._as_order_view().read_item_lines()

    def payment_methods_offered(self) -> list[str]:
        return [o.strip() for o in combo_options(self._field("payment_method"))]

    def select_payment_method(self, name: str) -> None:
        select_combo_option(self._field("payment_method"), name, spec_step="5.2", field_name="payment method")

    def mark_paid(self, payment_date: date, value: Decimal) -> None:
        set_checkbox(self._field("paid"), True, spec_step="5.3", field_name="paid")
        set_cdatetime(  # the 'at' date appears once 'paid' is ticked
            self._field("payment_date"),
            payment_date,
            enter_from=self._field("payment_method"),  # the date follows the method combo
            parse_format=self._ctx.ui_date_parse_format,
            commit=self._field("paid_value").set_focus,
            spec_step="5.3",
            field_name="payment date",
        )
        set_and_verify(self._field("paid_value"), f"{value:.2f}", spec_step="5.3", field_name="Value", normalize=_money)

    def read_payment_state(self) -> dict[str, str]:
        paid = bool(self._field("paid").iface_toggle.CurrentToggleState)
        state = {"paid": "true" if paid else "false"}
        if paid:
            state["date"] = self._iso(read_value(self._field("payment_date")))
            state["value"] = read_value(self._field("paid_value"))
        return state

    def save(self) -> None:
        self._ctx.save_editor(self._require_tab())

    # --- helpers ---------------------------------------------------------------------------------
    def _pane(self) -> Any:
        return self._ctx.editor_pane(self._require_tab())

    def _require_tab(self) -> EditorTab:
        if self._tab is None:
            raise ManualReviewRequired("4.7", ReviewReason.UI_ELEMENT_NOT_FOUND, "linked Invoice editor not open")
        return self._tab

    def _field(self, key: str) -> Any:
        return self._ctx.find(S, key, scope=self._pane())

    def _totals(self) -> dict[str, str]:
        return self._as_order_view().read_totals()

    def _as_order_view(self) -> OrderEditorScreen:
        """The Invoice editor shares the Order editor's layout for addresses, items and totals."""
        return OrderEditorScreen.for_existing_tab(self._ctx, self._require_tab())

    def _iso(self, text: str) -> str:
        try:
            return datetime.strptime(text.strip(), self._ctx.ui_date_parse_format).date().isoformat()
        except ValueError:
            return text


def _money(text: str) -> str:
    try:
        return f"{parse_amount(text):.2f}"
    except Exception:
        return text.strip()
