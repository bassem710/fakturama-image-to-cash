"""The Order editor (spec 1.3-1.8, 2.1, 2.4, 3.2, 3.13-3.16, 4.1-4.7). Selectors verified by discovery,
except the Items grid columns (OCR, see config/selectors.yaml)."""

from __future__ import annotations

import time
from datetime import date
from functools import partial
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.date_input import has_keyboard_focus, set_cdatetime
from imagetocash.automation.input import (
    escape_send_keys,
    read_value,
    select_combo_option,
    set_and_verify,
)
from imagetocash.automation.locators import largest_leaf_pane
from imagetocash.automation.waiting import wait_until
from imagetocash.domain.models import LineItem
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import parse_amount
from imagetocash.fakturama.screen_context import EditorTab, ScreenContext
from imagetocash.fakturama.screens.selection_dialog import SelectionDialogScreen

S = "order_editor"


class OrderEditorScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._title_prefix = str(ctx.selectors.value(S, "tab_title"))
        self._tab: EditorTab | None = None
        self._number = ""
        self.tabs_before_follow_up: dict[tuple[int, ...], int] = {}

    @classmethod
    def for_existing_tab(cls, ctx: ScreenContext, tab: EditorTab) -> OrderEditorScreen:
        """Read-only reuse of this editor's locators on another document tab with the same layout."""
        screen = cls(ctx)
        screen._tab = tab
        return screen

    # --- 1.3-1.8 ---------------------------------------------------------------------------------
    def open_new_order(self) -> None:
        """1.3: a NEW Order editor, tracked by identity; a leftover 'New Order' draft is ignored."""
        self._ctx.session.bring_to_front()
        before = self._ctx.tab_snapshot()
        self._ctx.press(self._ctx.find("main", "new_order"))
        self._tab = self._ctx.wait_for_new_tab(before, title_prefix=self._title_prefix)
        self._ctx.find(S, "customer_reference", scope=self._pane())  # editor is ready

    def activate(self) -> None:
        self._ctx.activate_editor(self._require_tab())

    def read_document_number(self) -> str:
        self._number = read_value(self._field("number"))
        return self._number

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
        select_combo_option(self._field("price_mode"), "Net", spec_step="1.7", field_name="price mode")

    def read_vat_mode(self) -> str:
        return read_value(self._field("vat_mode"))

    # --- 2.1 / 2.4 / 3.2 ---------------------------------------------------------------------------
    def open_address_selector(self) -> SelectionDialogScreen:
        return self._open_selector("select_address", "address_title", "address_columns")

    def open_product_selector(self) -> SelectionDialogScreen:
        return self._open_selector("select_product", "product_title", "product_columns")

    def read_address_texts(self) -> dict[str, str]:
        """Each role is a tab of one tab folder; select it and read its multi-line address Edit."""
        tabs: dict[str, str] = self._ctx.selectors.value(S, "address_tabs")
        pane, texts = self._pane(), {}
        for role, tab_name in tabs.items():
            item = next((t for t in pane.descendants(control_type="TabItem") if t.element_info.name == tab_name), None)
            if item is None:
                continue
            item.click_input()  # Select() reports success here without switching (seen live)
            folder = wait_until(
                partial(_tab_folder_named, pane, tab_name),
                timeout=self._ctx.settings.timeouts.element,
                what=f"{tab_name} tab",
            )
            edit = next(iter(folder.descendants(control_type="Edit")), None)
            texts[role] = read_value(edit) if edit is not None else ""
        self._select_address_tab(pane, next(iter(tabs.values())))
        return texts

    def _select_address_tab(self, pane: Any, tab_name: str) -> None:
        """Leave the FIRST address tab (Invoice address) selected, as the editor had it. Found live
        (run #21, Fakturama 2.2.0 DocumentEditor.doSave line 412): Save looks up the address binding
        of the SELECTED address tab, which exists only for the tab that was selected when the Debtor
        was applied; with 'Delivery address' left selected, Save throws a NullPointerException and
        the Order stays unsaved."""
        item = next((t for t in pane.descendants(control_type="TabItem") if t.element_info.name == tab_name), None)
        if item is None:
            raise ManualReviewRequired("4.4", ReviewReason.UI_ELEMENT_NOT_FOUND, f"{tab_name} tab")
        item.click_input()
        wait_until(
            partial(_tab_folder_named, pane, tab_name),
            timeout=self._ctx.settings.timeouts.element,
            what=f"{tab_name} tab",
        )

    # --- 3.13-3.16 Items grid (custom-drawn NatTable -> OCR inside its UIA rectangle) ------------------
    def read_item_lines(self) -> list[dict[str, str]]:
        return self._ctx.read_table_rows(
            self._items_table(), self._item_columns(), self._item_order(), percent_fields=("vat", "discount")
        )

    def fill_item_line(self, line_index: int, item: LineItem) -> None:
        """Keyboard only: Ctrl+Home to the first cell, Down to the line, Right to the column (its index
        in the configured display order, never a pixel position), type the value, Enter."""
        rows = self.read_item_lines()
        if line_index >= len(rows):
            raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, f"no Items line {line_index + 1}")
        record = rows[line_index]
        wanted = {
            "quantity": format(item.quantity.normalize(), "f"),
            "unit_price": f"{item.unit_net_price:.2f}",
            "discount": format(item.discount_percent.normalize(), "f"),
        }
        order = self._item_order()
        table = self._items_table()

        def wrong(rec: dict[str, str]) -> list[str]:
            return [f for f, v in wanted.items() if not (rec.get(f) and _same_number(rec[f], v))]

        # Found live (run #19): on the first edit after a new line, leading navigation keys can be
        # lost, so a value lands in an EARLIER column (U.Price typed into Qty.). So every pass edits
        # the fields still wrong and then re-reads the WHOLE line; a second pass repairs, else stop.
        for _pass in range(2):
            for field in wrong(record):  # 3.14: "set or confirm"
                table.set_focus()
                wait_until(lambda: has_keyboard_focus(table), timeout=2, what="Items table focus")
                time.sleep(0.2)  # run #16: keys sent right after the focus change were dropped
                # Run #18: Fakturama can leave a cell editor open; keys then go INTO it and it hides
                # the table. Escape first (no edit in progress) and after the commit.
                keys = "{ESC}^{HOME}" + "{DOWN}" * line_index + "{RIGHT}" * order.index(field)
                keyboard.send_keys(keys, pause=0.05)
                keyboard.send_keys(escape_send_keys(wanted[field]) + "{ENTER}", pause=0.05)  # opens the editor
                keyboard.send_keys("{ESC}", pause=0.05)
            self._ctx.invalidate()
            lines = self.read_item_lines()
            record = dict(lines[line_index]) if line_index < len(lines) else {}  # short read: not verified
            if not wrong(record):
                break
        if still := wrong(record):
            raise ManualReviewRequired(
                "3.13", ReviewReason.VALUE_MISMATCH, f"{item.sku}: {', '.join(still)} not set after 2 passes"
            )
        if not _same_number(record.get("vat", ""), str(item.vat_percent)):
            raise ManualReviewRequired(
                "3.14",
                ReviewReason.VALUE_MISMATCH,
                f"{item.sku}: line VAT {record.get('vat')!r} != {item.vat_percent}%",
            )

    # --- 4.2-4.7 ------------------------------------------------------------------------------------------
    def ensure_order_level_defaults(self) -> None:
        discount = self._field("discount")
        if not _same_number(read_value(discount), "0"):
            set_and_verify(discount, "0", spec_step="4.2", field_name="Discount", normalize=_number_text)
        shipping = read_value(self._field("shipping"))
        if "free" not in shipping.casefold():
            raise ManualReviewRequired("4.2", ReviewReason.VALUE_MISMATCH, f"Shipping is {shipping!r}")

    def read_totals(self) -> dict[str, str]:
        return {
            "net": read_value(self._field("total_net")),
            "vat": read_value(self._field("vat_total")),
            "total": read_value(self._field("total")),
        }

    def save(self) -> None:
        self._ctx.save_editor(self._require_tab())

    def create_follow_up_invoice(self) -> None:
        """4.6: the 'Create a follow-up document' group's Invoice button keeps the Order link."""
        self.activate()
        self.tabs_before_follow_up = self._ctx.tab_snapshot()
        self._ctx.press(self._field("follow_up_invoice"))

    # --- helpers ----------------------------------------------------------------------------------------
    def _require_tab(self) -> EditorTab:
        if self._tab is None:
            raise ManualReviewRequired("1.8", ReviewReason.UI_ELEMENT_NOT_FOUND, "no Order editor opened")
        return self._tab

    def _pane(self) -> Any:
        return self._ctx.editor_pane(self._require_tab())

    def _field(self, key: str) -> Any:
        return self._ctx.find(S, key, scope=self._pane())

    def _item_columns(self) -> dict[str, str]:
        return dict(self._ctx.selectors.value(S, "items_columns"))

    def _items_table(self) -> Any:
        """The NatTable sits in the pane to the right of the 'Items' label's container (verified layout)."""
        label = self._ctx.find(S, "select_product", scope=self._pane()).parent()
        siblings = list(label.parent().children())
        after = siblings[siblings.index(label) + 1 :] if label in siblings else siblings
        for candidate in after:
            table = largest_leaf_pane(candidate) if candidate.children() else candidate
            if table is not None:
                return table
        raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, "Items table not found")

    def _item_order(self) -> list[str]:
        return list(self._ctx.selectors.value(S, "items_order"))

    def _open_selector(self, icon_key: str, title_key: str, columns_key: str) -> SelectionDialogScreen:
        self.activate()
        self._ctx.press(self._ctx.find(S, icon_key, scope=self._pane()))  # Image icon: no pattern -> element click
        title = str(self._ctx.selectors.value("selection_dialogs", title_key))
        dialog = self._ctx.session.wait_for_dialog(title, self._ctx.settings.timeouts.dialog)
        columns = dict(self._ctx.selectors.value("selection_dialogs", columns_key))
        order = list(self._ctx.selectors.value("selection_dialogs", columns_key.replace("_columns", "_order")))
        return SelectionDialogScreen(self._ctx, dialog, title, columns, order)


def _tab_folder_named(pane: Any, name: str) -> Any | None:
    """A tab folder's UIA name is the title of its selected tab."""
    return next((f for f in pane.descendants(control_type="Tab") if f.element_info.name == name), None)


def _number_text(text: str) -> str:
    try:
        return format(parse_amount(text).normalize(), "f")
    except Exception:
        return text.strip()


def _same_number(a: str, b: str) -> bool:
    return _number_text(a) == _number_text(b)
