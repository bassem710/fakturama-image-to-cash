"""Data views (terms of payment, VATs, Documents) and the small record editors their green + opens
(spec 2.10.1-2.10.6, 3.4-3.6)."""

from __future__ import annotations

import time
from decimal import Decimal

from imagetocash.automation.input import read_value, select_combo_option, set_and_verify
from imagetocash.automation.locators import locate
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.matching import normalize_ocr_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.row_choice import open_row_with_pointer
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.base_editor import EditorScreen
from imagetocash.fakturama.values import is_zero, number_text
from imagetocash.fakturama.workbench import EditorTab

L = "lists"
# An EMPTY search result is only believed once the list has stayed empty this long: while it
# re-filters it can be blank for a moment, and "no rows" lets the caller CREATE a record.
EMPTY_CONFIRM_SECONDS = 0.5  # an OCR look takes 0.2-0.5 s: still two or more empty reads in a row


class MasterDataListScreen:
    """A Data view: search box (typed, read back), custom-drawn list (clipboard copy, OCR as
    fallback), green + (the view toolbar's 'Create...' button, Invoke).

    `name` selects the selectors.yaml entries: data_views.<view>, lists.<name>_columns and
    lists.<name>_order."""

    def __init__(self, ctx: ScreenContext, view: str, name: str, percent_fields: tuple[str, ...] = ()) -> None:
        self._ctx, self._view_key = ctx, view
        self._columns = dict(ctx.selectors.value(L, f"{name}_columns"))
        self._order = list(ctx.selectors.value(L, f"{name}_order"))
        self._percent_fields = percent_fields
        self._title = ""

    def open(self) -> None:
        self._title = self._ctx.workbench.open_data_view(self._view_key)

    def search(self, text: str) -> list[dict[str, str]]:
        workbench = self._ctx.workbench
        if not self._title:
            self.open()
        workbench.activate_view(self._title)
        pane = workbench.content_pane(self._title)
        set_and_verify(
            locate(pane, self._ctx.selectors.locator(L, "search")), text, spec_step="-", field_name="list search"
        )
        table = self._ctx.lists.table_in(pane)
        wanted = normalize_ocr_text(text)
        empty_since: list[float] = []

        def filtered() -> list[dict[str, str]] | None:
            """The list re-filters asynchronously: accept a read only once every row contains the
            search text, so a stale, unfiltered list is never taken as the answer, and an empty read
            only once it stays empty (EMPTY_CONFIRM_SECONDS)."""
            rows = self._ctx.lists.read(table, self._columns, self._order, self._percent_fields)
            if not rows:
                empty_since[:] = empty_since or [time.monotonic()]
                return rows if time.monotonic() - empty_since[0] >= EMPTY_CONFIRM_SECONDS else None
            empty_since.clear()
            return rows if all(wanted in normalize_ocr_text(" ".join(r.values())) for r in rows) else None

        return wait_until(
            filtered,
            done=lambda rows: rows is not None,
            timeout=self._ctx.settings.timeouts.list_stable,
            what="the filtered list",
        )

    def create_new(self) -> None:
        """The green + at the upper right of the list: the view's own 'Create...' toolbar button."""
        workbench = self._ctx.workbench
        folder = workbench.view_folder(self._title)
        before = workbench.snapshot()
        self._ctx.press(locate(folder, self._ctx.selectors.locator(L, "create_new")))
        self._ctx.last_record_editor = workbench.wait_for_new(before)


class VatListScreen(MasterDataListScreen):
    """Data > VATs. The list shows Name, Description and Value but not the VAT code (spec 3.5 needs
    it), and Fakturama opens a row only by double-clicking it (no keyboard or pattern route; verified
    live). So each row named like the wanted rate is opened through the pointer exception
    (row_choice.py, found by its Name and Value), its 'VAT code (E-Invoice)' is read, and the list
    view is brought back. The opened editor is only read: never edited or saved."""

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx, "vats", "vat", percent_fields=("value",))
        self._pick_fields = list(ctx.selectors.value(L, "vat_pick"))

    def search(self, text: str) -> list[dict[str, str]]:
        rows = super().search(text)
        named = [r for r in rows if normalize_ocr_text(r.get("name", "")) == normalize_ocr_text(text)]
        known = self._ctx.saved_vat_codes.get(text)
        if known is not None and len(named) == 1:  # the one rate of that name is the one 3.6 saved
            named[0]["code"] = known
            get_logger().info("3.5     VAT code known from 3.6 in this run (editor not reopened)")
            return rows
        for record in named:
            record["code"] = self._read_code(record)
        return rows

    def _read_code(self, record: dict[str, str]) -> str:
        ctx, workbench = self._ctx, self._ctx.workbench
        table = ctx.lists.table_in(workbench.content_pane(self._title))
        before = workbench.snapshot()
        open_row_with_pointer(table, ctx.ocr, self._columns, record, self._pick_fields)
        name = record.get("name", "")
        try:  # a new tab, or the rate's already open editor brought to the front (e.g. the one 3.6 saved)
            tab = workbench.wait_for_record_editor(before, name)
        except WaitTimeout as error:
            raise ManualReviewRequired(
                "3.5", ReviewReason.UI_ELEMENT_NOT_FOUND, f"could not open {name!r} to read its VAT code"
            ) from error
        if workbench.is_dirty(tab):  # unsaved edits: the code on screen may not be the stored one
            raise ManualReviewRequired("3.5", ReviewReason.CONFLICTING_MATCH, f"{name!r} has unsaved changes open")
        pane = workbench.pane(tab)
        shown_name = read_value(ctx.find("vat_editor", "name", scope=pane))
        if normalize_ocr_text(shown_name) != normalize_ocr_text(name):  # the double-click opened another rate
            raise ManualReviewRequired(
                "3.5", ReviewReason.CONFLICTING_MATCH, f"opened {shown_name!r} instead of {name!r}"
            )
        code = read_value(ctx.find("vat_editor", "code", scope=pane))
        get_logger().info("3.5     VAT code of the existing rate read from its editor (left open, unchanged)")
        workbench.activate_view(self._title)
        return code


class RecordEditorScreen(EditorScreen):
    """A small record editor opened by a list's green + (it becomes ctx.last_record_editor)."""

    opened_at = "-"

    @property
    def tab(self) -> EditorTab:
        if self._ctx.last_record_editor is None:
            raise ManualReviewRequired(self.opened_at, ReviewReason.UI_ELEMENT_NOT_FOUND, "no record editor opened")
        return self._ctx.last_record_editor


class PaymentMethodEditorScreen(RecordEditorScreen):
    section = "payment_method_editor"
    opened_at = "2.10.2"

    def fill(self, name: str, payment_code: str) -> None:
        set_and_verify(self._field("name"), name, spec_step="2.10.3", field_name="Name")
        set_and_verify(self._field("description"), name, spec_step="2.10.3", field_name="Description")
        select_combo_option(self._field("payment_code"), payment_code, spec_step="2.10.4", field_name="payment code")
        for key in ("cash_discount", "discount_days", "net_days"):
            field = self._field(key)
            if not is_zero(read_value(field)):
                set_and_verify(field, "0", spec_step="2.10.5", field_name=key, normalize=number_text)


class VatEditorScreen(RecordEditorScreen):
    section = "vat_editor"
    opened_at = "3.6"

    def fill(self, name: str, percent: Decimal) -> None:
        set_and_verify(self._field("name"), name, spec_step="3.6", field_name="Name")
        set_and_verify(self._field("description"), name, spec_step="3.6", field_name="Description")
        standard = self._word("standard_code_option")
        code = self._field("code")
        if not read_value(code).strip().upper().startswith(standard[0]):
            select_combo_option(code, standard, spec_step="3.6", field_name="VAT code")
        self._ctx.saved_vat_codes[name] = read_value(code)  # saved right after (3.6); reused at 3.5
        value = format(percent.normalize(), "f")
        set_and_verify(self._field("value"), value, spec_step="3.6", field_name="Value", normalize=number_text)
