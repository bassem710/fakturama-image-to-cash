"""The Order editor (spec 1.3-1.8, 2.1, 2.4, 3.2, 3.13-3.16, 4.1-4.7). Selectors verified by discovery,
except the Items grid columns (OCR, see config/selectors.yaml)."""

from __future__ import annotations

from datetime import date
from functools import partial
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import escape_send_keys, read_value, select_combo_option, set_and_verify
from imagetocash.automation.locators import largest_leaf_pane
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.automation.waiting import wait_until
from imagetocash.domain.models import LineItem
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import parse_amount
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.selection_dialog import SelectionDialogScreen

S = "order_editor"


class OrderEditorScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._title = str(ctx.selectors.value(S, "tab_title"))
        self._number = ""
        self.tabs_before_follow_up: list[str] = []

    @classmethod
    def for_existing_tab(cls, ctx: ScreenContext, title: str) -> OrderEditorScreen:
        """Read-only reuse of this editor's locators on another document tab with the same layout."""
        screen = cls(ctx)
        screen._title = title
        return screen

    # --- 1.3-1.8 ---------------------------------------------------------------------------------
    def open_new_order(self) -> None:
        self._ctx.session.bring_to_front()
        before = self._ctx.tab_titles()
        self._ctx.press(self._ctx.find("main", "new_order"))
        self._title = self._ctx.wait_for_new_tab(before, title_prefix=self._title)
        self._ctx.find(S, "customer_reference", scope=self._pane())  # editor is ready

    def activate(self) -> None:
        candidates = [self._title, self._number]
        title = next((t for t in candidates if t and t in [x.lstrip("*") for x in self._ctx.tab_titles()]), None)
        if title is None:
            raise ManualReviewRequired("1.8", ReviewReason.UI_ELEMENT_NOT_FOUND, "the open Order tab disappeared")
        self._title = title
        self._ctx.activate_tab(title)

    def read_document_number(self) -> str:
        self._number = read_value(self._field("number"))
        return self._number

    def set_order_date(self, value: date) -> None:
        text = self._ctx.format_ui_date(value)
        set_and_verify(self._field("date"), text, spec_step="1.5", field_name="Date")

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
            item.iface_selection_item.Select()
            folder = wait_until(
                partial(_tab_folder_named, pane, tab_name),
                timeout=self._ctx.settings.timeouts.element,
                what=f"{tab_name} tab",
            )
            edit = next(iter(folder.descendants(control_type="Edit")), None)
            texts[role] = read_value(edit) if edit is not None else ""
        return texts

    # --- 3.13-3.16 Items grid (custom-drawn NatTable -> OCR inside its UIA rectangle) ------------------
    def read_item_lines(self) -> list[dict[str, str]]:
        return [record for record, _ in self._ctx.read_table_rows(self._items_table(), self._item_columns())]

    def fill_item_line(self, line_index: int, item: LineItem) -> None:
        columns = self._item_columns()
        title_of = {field: title for title, field in columns.items()}
        rows = self._ctx.read_table_rows(self._items_table(), columns)
        if line_index >= len(rows):
            raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, f"no Items line {line_index + 1}")
        record, ocr_row = rows[line_index]
        wanted = {
            "quantity": format(item.quantity.normalize(), "f"),
            "unit_price": f"{item.unit_net_price:.2f}",
            "discount": format(item.discount_percent.normalize(), "f"),
        }
        for field, value in wanted.items():
            if record.get(field) and _same_number(record[field], value):
                continue  # 3.14: "set or confirm"
            x = self._column_x(title_of[field])
            self._ctx.click_point((int(x), ocr_row.click_point[1]), double=True)
            keyboard.send_keys("^a" + escape_send_keys(value) + "{ENTER}", pause=0.02)
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
        self.activate()
        self._ctx.save_via_toolbar(self._title)

    def create_follow_up_invoice(self) -> None:
        """4.6: the 'Create a follow-up document' group's Invoice button keeps the Order link."""
        self.activate()
        self.tabs_before_follow_up = self._ctx.tab_titles()
        self._ctx.press(self._field("follow_up_invoice"))

    # --- helpers ----------------------------------------------------------------------------------------
    def _pane(self) -> Any:
        return self._ctx.content_pane(self._title)

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

    def _column_x(self, title: str) -> float:
        ocr_table = self._ctx.tables.read(
            ScreenRect.of(self._items_table()), expected_headers=tuple(self._item_columns())
        )
        x = ocr_table.column_center_x(title)
        if x is None:
            raise ManualReviewRequired("3.13", ReviewReason.UI_ELEMENT_NOT_FOUND, f"Items column {title!r} not found")
        return x

    def _open_selector(self, icon_key: str, title_key: str, columns_key: str) -> SelectionDialogScreen:
        self.activate()
        self._ctx.find(S, icon_key, scope=self._pane()).click_input()  # Image: no Invoke pattern
        title = str(self._ctx.selectors.value("selection_dialogs", title_key))
        dialog = self._ctx.session.wait_for_dialog(title, self._ctx.settings.timeouts.dialog)
        columns = dict(self._ctx.selectors.value("selection_dialogs", columns_key))
        return SelectionDialogScreen(self._ctx, dialog, title, columns)


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
