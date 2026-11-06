"""The Order editor (spec 1.3-1.8, 2.1, 2.4, 3.2, 3.13-3.16, 4.1-4.7).

The Items grid is a NatTable: read by clipboard copy (fakturama/tables.py), edited by keyboard only
(Ctrl+Home, Down to the line, Right to the column by its index in the configured column order).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.date_input import set_cdatetime
from imagetocash.automation.focus import focus
from imagetocash.automation.input import escape_send_keys, read_value, select_combo_option, set_and_verify
from imagetocash.automation.locators import find_first, largest_leaf_pane
from imagetocash.automation.waiting import wait_until
from imagetocash.domain.models import LineItem
from imagetocash.domain.pricing import round_money
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.base_editor import EditorScreen
from imagetocash.fakturama.screens.selection_dialog import SelectionDialogScreen
from imagetocash.fakturama.values import number_text, same_number
from imagetocash.fakturama.workbench import EditorTab

NAV_KEY_PAUSE = 0.05  # navigation keys right after a focus change can be lost (measured)
VALUE_KEY_PAUSE = 0.02


class OrderEditorScreen(EditorScreen):
    section = "order_editor"
    opened_at = "1.3"

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx)
        self.tabs_before_follow_up: dict[tuple[int, ...], int] = {}

    @classmethod
    def for_existing_tab(cls, ctx: ScreenContext, tab: EditorTab) -> OrderEditorScreen:
        """This editor's locators on another document tab with the same layout (the Invoice)."""
        screen = cls(ctx)
        screen._tab = tab
        return screen

    # --- 1.3-1.8 ---------------------------------------------------------------------------------
    def open_new_order(self) -> None:
        """1.3: a NEW Order editor, tracked by identity; a leftover 'New Order' draft is ignored."""
        workbench = self._ctx.workbench
        self._ctx.session.bring_to_front()
        before = workbench.snapshot()
        self._ctx.press(self._ctx.find("main", "new_order"))
        self._tab = workbench.wait_for_new(before, title_prefix=self._word("tab_title"))
        self._field("customer_reference")  # the editor is ready

    def read_document_number(self) -> str:
        return read_value(self._field("number"))

    def set_order_date(self, value: date) -> None:
        set_cdatetime(
            self._field("date"),
            value,
            enter_from=self._field("number"),  # Tab from No. selects the date's first part (verified)
            parse_format=self._ctx.ui_date_parse_format,
            commit=self._field("customer_reference").set_focus,
            spec_step="1.5",
            field_name="Date",
        )

    def set_customer_reference(self, value: str) -> None:
        set_and_verify(self._field("customer_reference"), value, spec_step="1.6", field_name="Cust.Ref.")

    def set_price_mode_net(self) -> None:
        select_combo_option(
            self._field("price_mode"), self._word("price_mode_net"), spec_step="1.7", field_name="price mode"
        )

    def read_vat_mode(self) -> str:
        return read_value(self._field("vat_mode"))

    # --- 2.1 / 2.4 / 3.2 ---------------------------------------------------------------------------
    def open_address_selector(self) -> SelectionDialogScreen:
        return self._open_selector("select_address", "address")

    def open_product_selector(self) -> SelectionDialogScreen:
        return self._open_selector("select_product", "product")

    def read_address_texts(self) -> dict[str, str]:
        """Each role is a tab of one tab folder; select it and read its multi-line address Edit.
        Ends with the FIRST tab (Invoice address) selected again: Fakturama's Save fails while
        'Delivery address' is selected (docs/control-map.md, Gotchas)."""
        tabs: dict[str, str] = self._ctx.selectors.value(self.section, "address_tabs")
        pane, texts = self._pane(), {}
        for role, tab_name in tabs.items():
            folder = self._select_address_tab(pane, tab_name)
            if folder is None:
                continue
            edit = find_first(folder, control_type="Edit")
            texts[role] = read_value(edit) if edit is not None else ""
        self._select_address_tab(pane, next(iter(tabs.values())))
        return texts

    def _select_address_tab(self, pane: Any, tab_name: str) -> Any | None:
        """Select an address tab (a click: Select() reports success here without switching) and return
        its content folder; None when the editor has no such tab."""
        item = find_first(pane, control_type="TabItem", name=tab_name)
        if item is None:
            return None
        item.click_input()
        return wait_until(
            lambda: find_first(pane, control_type="Tab", name=tab_name),  # a folder is named after its tab
            timeout=self._ctx.settings.timeouts.element,
            what=f"{tab_name} tab",
        )

    # --- 3.13-3.16 Items grid --------------------------------------------------------------------
    def read_item_lines(self) -> list[dict[str, str]]:
        return self._read_items(self._items_table())

    def fill_item_line(self, line_index: int, item: LineItem) -> dict[str, str]:
        """3.13-3.15 by keyboard; returns the line as read back after the edit (verified).

        Leading navigation keys can be lost on the first edit after a new line, landing a value in an
        EARLIER column, so every pass edits the fields still wrong and then re-reads the WHOLE line;
        a second pass repairs, else the run stops."""
        table = self._items_table()
        record = self._line(table, line_index)
        wanted = {
            "quantity": format(item.quantity.normalize(), "f"),
            "unit_price": str(round_money(item.unit_net_price)),
            "discount": format(item.discount_percent.normalize(), "f"),
        }
        order = self._item_order()

        def wrong(rec: dict[str, str]) -> list[str]:
            return [f for f, v in wanted.items() if not (rec.get(f) and same_number(rec[f], v))]

        for _pass in range(2):
            fields = wrong(record)
            if not fields:
                break  # 3.14: "set or confirm"
            focus(table)
            for field in fields:
                # Escape first: Fakturama can leave a cell editor open, and keys would go into it.
                keyboard.send_keys(
                    "{ESC}^{HOME}" + "{DOWN}" * line_index + "{RIGHT}" * order.index(field), pause=NAV_KEY_PAUSE
                )
                keyboard.send_keys(escape_send_keys(wanted[field]) + "{ENTER}", pause=VALUE_KEY_PAUSE)
                keyboard.send_keys("{ESC}", pause=NAV_KEY_PAUSE)  # close the editor Enter may reopen
            self._ctx.invalidate()
            record = self._line(table, line_index, required=False)
        if still := wrong(record):
            raise ManualReviewRequired(
                "3.13", ReviewReason.VALUE_MISMATCH, f"{item.sku}: {', '.join(still)} not set after 2 passes"
            )
        if not same_number(record.get("vat", ""), str(item.vat_percent)):
            raise ManualReviewRequired(
                "3.14",
                ReviewReason.VALUE_MISMATCH,
                f"{item.sku}: line VAT {record.get('vat')!r} != {item.vat_percent}%",
            )
        return record

    # --- 4.2-4.7 ------------------------------------------------------------------------------------------
    def ensure_order_level_defaults(self) -> None:
        discount = self._field("discount")
        if not same_number(read_value(discount), "0"):
            set_and_verify(discount, "0", spec_step="4.2", field_name="Discount", normalize=number_text)
        shipping = read_value(self._field("shipping"))
        if self._word("shipping_free_word").casefold() not in shipping.casefold():
            raise ManualReviewRequired("4.2", ReviewReason.VALUE_MISMATCH, f"Shipping is {shipping!r}")

    def read_totals(self) -> dict[str, str]:
        return {
            "net": read_value(self._field("total_net")),
            "vat": read_value(self._field("vat_total")),
            "total": read_value(self._field("total")),
        }

    def create_follow_up_invoice(self) -> None:
        """4.6: the 'Create a follow-up document' group's Invoice button keeps the Order link."""
        self.activate()
        self.tabs_before_follow_up = self._ctx.workbench.snapshot()
        self._ctx.press(self._field("follow_up_invoice"))

    # --- helpers ----------------------------------------------------------------------------------------
    def _items_table(self) -> Any:
        """The NatTable sits in the pane to the right of the 'Items' label's container (verified layout)."""
        label = self._field("select_product").parent()
        siblings = list(label.parent().children())
        after = siblings[siblings.index(label) + 1 :] if label in siblings else siblings
        for candidate in after:
            table = largest_leaf_pane(candidate) if candidate.children() else candidate
            if table is not None:
                return table
        raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, "Items table not found")

    def _read_items(self, table: Any) -> list[dict[str, str]]:
        """The Items grid is read only once a line exists, so no empty-list check is needed."""
        columns = dict(self._ctx.selectors.value(self.section, "items_columns"))
        return self._ctx.lists.read(table, columns, self._item_order(), ("vat", "discount"), may_be_empty=False)

    def _line(self, table: Any, line_index: int, *, required: bool = True) -> dict[str, str]:
        lines = self._read_items(table)
        if line_index < len(lines):
            return dict(lines[line_index])
        if required:
            raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, f"no Items line {line_index + 1}")
        return {}  # a short read: nothing verified, the next pass edits again

    def _item_order(self) -> list[str]:
        return list(self._ctx.selectors.value(self.section, "items_order"))

    def _open_selector(self, icon_key: str, kind: str) -> SelectionDialogScreen:
        self.activate()
        self._ctx.press(self._field(icon_key))  # Image icon: no pattern -> element click
        return SelectionDialogScreen.open(self._ctx, kind)
