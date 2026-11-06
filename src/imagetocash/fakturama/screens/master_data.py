"""Data > terms of payment / Data > VATs lists and their small editors (spec 2.10.1-2.10.6, 3.4-3.6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import read_value, select_combo_option, set_and_verify, type_into
from imagetocash.automation.locators import locate
from imagetocash.automation.ocr_table import OcrTableRow
from imagetocash.domain.matching import normalize_ocr_text
from imagetocash.fakturama.screen_context import ScreenContext


class MasterDataListScreen:
    """A Data view: search box (UIA, label 'Search:'), custom-drawn list (OCR), green + (UIA toolbar)."""

    def __init__(self, ctx: ScreenContext, view_key: str, columns_key: str) -> None:
        self._ctx, self._view_key, self._columns_key = ctx, view_key, columns_key
        self._title = ""

    def open(self) -> None:
        self._title = self._ctx.open_data_view(self._view_key)

    def search(self, text: str) -> list[dict[str, str]]:
        return [record for record, _ in self._search_rows(text)]

    def _search_rows(self, text: str) -> list[tuple[dict[str, str], OcrTableRow]]:
        pane = self._view()
        type_into(locate(pane, self._ctx.selectors.locator("lists", "search")), text, commit_key="")
        columns = dict(self._ctx.selectors.value("lists", self._columns_key))
        return self._ctx.read_table_rows(self._ctx.table_in(pane), columns)

    def create_new(self) -> None:
        """The green + at the upper right of the list: the view's own 'Create…' toolbar button."""
        tab = next(t for t in self._ctx.main().descendants(control_type="Tab") if t.element_info.name == self._title)
        before = self._ctx.tab_titles()
        self._ctx.press(locate(tab, self._ctx.selectors.locator("lists", "create_new")))
        self._ctx.wait_for_new_tab(before)

    def _view(self) -> Any:
        if not self._title:
            self.open()
        self._ctx.activate_tab(self._title)
        return self._ctx.content_pane(self._title)


class VatListScreen(MasterDataListScreen):
    """Data > VATs. The list has no 'VAT code' column, so spec 3.5's code check opens each row whose
    name matches (double-click at its OCR-measured point), reads 'VAT code (E-Invoice)' and closes
    the unchanged editor again (Ctrl+W)."""

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx, "vats", "vat_columns")

    def search(self, text: str) -> list[dict[str, str]]:
        rows = []
        for record, ocr_row in self._search_rows(text):
            if normalize_ocr_text(record.get("name", "")) == normalize_ocr_text(text):
                record["code"] = self._read_code(ocr_row)
            rows.append(record)
        return rows

    def _read_code(self, ocr_row: OcrTableRow) -> str:
        before = self._ctx.tab_titles()
        self._ctx.click_point(ocr_row.click_point, double=True)
        title = self._ctx.wait_for_new_tab(before)
        try:
            return read_value(self._ctx.find("vat_editor", "code", scope=self._ctx.content_pane(title)))
        finally:
            self._ctx.activate_tab(title)
            keyboard.send_keys("^w")
            self._ctx.activate_tab(self._title)


class _SmallEditor:
    screen = ""

    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx

    def _editor(self) -> Any:
        selected = [t for t in self._ctx.tab_items() if t.iface_selection_item.CurrentIsSelected]
        title = str(selected[-1].element_info.name).lstrip("*") if selected else ""
        return self._ctx.content_pane(title)

    def _field(self, key: str) -> Any:
        return self._ctx.find(self.screen, key, scope=self._editor())

    def save(self) -> None:
        selected = [t for t in self._ctx.tab_items() if t.iface_selection_item.CurrentIsSelected]
        self._ctx.save_via_toolbar(str(selected[-1].element_info.name).lstrip("*"))


class PaymentMethodEditorScreen(_SmallEditor):
    screen = "payment_method_editor"

    def fill(self, name: str, payment_code: str) -> None:
        set_and_verify(self._field("name"), name, spec_step="2.10.3", field_name="Name")
        set_and_verify(self._field("description"), name, spec_step="2.10.3", field_name="Description")
        select_combo_option(self._field("payment_code"), payment_code, spec_step="2.10.4", field_name="payment code")
        for key in ("cash_discount", "discount_days", "net_days"):
            field = self._field(key)
            if read_value(field).strip() not in {"0", "0%", "0.00", "0,00"}:
                set_and_verify(field, "0", spec_step="2.10.5", field_name=key)


class VatEditorScreen(_SmallEditor):
    screen = "vat_editor"

    def fill(self, name: str, percent: Decimal) -> None:
        set_and_verify(self._field("name"), name, spec_step="3.6", field_name="Name")
        set_and_verify(self._field("description"), name, spec_step="3.6", field_name="Description")
        code = self._field("code")
        if not read_value(code).strip().upper().startswith("S"):
            select_combo_option(code, "S (Standard rate)", spec_step="3.6", field_name="VAT code")
        value = format(percent.normalize(), "f")
        set_and_verify(self._field("value"), value, spec_step="3.6", field_name="Value", normalize=_digits)


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit() or ch == ".").rstrip("0").rstrip(".")
