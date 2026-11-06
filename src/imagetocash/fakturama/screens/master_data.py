"""Data > terms of payment / Data > VATs lists and their small editors (spec 2.10.1-2.10.6, 3.4-3.6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from imagetocash.automation.input import read_value, select_combo_option, set_and_verify
from imagetocash.automation.locators import locate
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.waiting import wait_until
from imagetocash.domain.matching import normalize_ocr_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import EditorTab, ScreenContext


class MasterDataListScreen:
    """A Data view: search box (UIA Value, read back), custom-drawn list (clipboard copy, OCR as
    fallback), green + (the view toolbar's 'Create...' button, Invoke)."""

    def __init__(
        self, ctx: ScreenContext, view_key: str, columns_key: str, percent_fields: tuple[str, ...] = ()
    ) -> None:
        self._ctx, self._view_key, self._columns_key = ctx, view_key, columns_key
        self._percent_fields = percent_fields
        self._title = ""

    def open(self) -> None:
        self._title = self._ctx.open_data_view(self._view_key)

    def search(self, text: str) -> list[dict[str, str]]:
        pane = self._view()
        box = locate(pane, self._ctx.selectors.locator("lists", "search"))
        set_and_verify(box, text, spec_step="-", field_name="list search")  # typed text must land
        columns = dict(self._ctx.selectors.value("lists", self._columns_key))
        order = list(self._ctx.selectors.value("lists", self._columns_key.replace("_columns", "_order")))
        table = self._ctx.table_in(pane)
        wanted = normalize_ocr_text(text)

        def filtered() -> list[dict[str, str]] | None:
            """The list re-filters asynchronously (seen live): accept a read only once every row
            contains the search text, so a stale, unfiltered list is never taken as the answer."""
            rows = self._ctx.read_table_rows(table, columns, order, self._percent_fields)
            ok = all(wanted in normalize_ocr_text(" ".join(record.values())) for record in rows)
            return rows if ok else None

        return wait_until(
            filtered,
            done=lambda rows: rows is not None,
            timeout=self._ctx.settings.timeouts.list_stable,
            what="the filtered list",
        )

    def create_new(self) -> None:
        """The green + at the upper right of the list: the view's own 'Create...' toolbar button."""
        tab = next(t for t in self._ctx.main().descendants(control_type="Tab") if t.element_info.name == self._title)
        before = self._ctx.tab_snapshot()
        self._ctx.press(locate(tab, self._ctx.selectors.locator("lists", "create_new")))
        self._ctx.last_record_editor = self._ctx.wait_for_new_tab(before)

    def _view(self) -> Any:
        if not self._title:
            self.open()
        self._ctx.activate_tab(self._title)
        return self._ctx.content_pane(self._title)


class VatListScreen(MasterDataListScreen):
    """Data > VATs. The list shows Name, Description and Value but not the VAT code, and Fakturama
    opens a row only by double-clicking it (no keyboard or pattern route; verified live). By your
    decision the code of a PRE-EXISTING rate is therefore not opened: rows carry code 'S' and the
    gap is logged. Rates the script creates always get code S (3.6)."""

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx, "vats", "vat_columns", percent_fields=("value",))

    def search(self, text: str) -> list[dict[str, str]]:
        rows = super().search(text)
        for record in rows:
            if normalize_ocr_text(record.get("name", "")) == normalize_ocr_text(text):
                record["code"] = "S"
                get_logger().info(
                    "3.5     VAT code of the existing rate not opened (no UIA route); Name and Value matched"
                )
        return rows


class _SmallEditor:
    screen = ""

    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx

    def _tab(self) -> EditorTab:
        if self._ctx.last_record_editor is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "no record editor opened")
        return self._ctx.last_record_editor

    def _editor(self) -> Any:
        return self._ctx.editor_pane(self._tab())

    def _field(self, key: str) -> Any:
        return self._ctx.find(self.screen, key, scope=self._editor())

    def save(self) -> None:
        self._ctx.save_editor(self._tab())


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
