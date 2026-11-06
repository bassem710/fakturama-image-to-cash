"""'Select the address' / 'Select a product' dialogs (spec 2.2-2.3, 2.12, 3.3, 3.12).
Search box and OK/Cancel through UIA; the result list is custom-drawn and read with OCR."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from imagetocash.automation.input import set_and_verify
from imagetocash.automation.locators import locate
from imagetocash.automation.ocr_table import OcrTableRow
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.automation.waiting import WaitTimeout
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext

S = "selection_dialogs"


class SelectionDialogScreen:
    def __init__(self, ctx: ScreenContext, dialog: Any, title: str, columns: Mapping[str, str]) -> None:
        self._ctx, self._dialog, self._title, self._columns = ctx, dialog, title, columns
        self._rows: list[tuple[dict[str, str], OcrTableRow]] = []

    def search(self, text: str) -> list[dict[str, str]]:
        search_box = locate(self._dialog, self._ctx.selectors.locator(S, "search"))
        set_and_verify(search_box, text, spec_step="-", field_name=f"{self._title} search")
        self._rows = self._ctx.read_table_rows(self._ctx.table_in(self._dialog), self._columns)
        return [dict(record) for record, _ in self._rows]

    def choose(self, row: Mapping[str, str]) -> None:
        match = next((ocr_row for record, ocr_row in self._rows if record == dict(row)), None)
        if match is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"row vanished from {self._title}")
        # Found live: clicking the row-number cell only highlights the row, and OK then applies
        # nothing. A double-click on a DATA cell selects the record and closes the dialog. The point
        # is measured by OCR inside the list's UIA rectangle (first mapped column, the row's y).
        table = self._ctx.tables.read(ScreenRect.of(self._ctx.table_in(self._dialog)), tuple(self._columns))
        x = next((x for title in self._columns if (x := table.column_center_x(title)) is not None), None)
        if x is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"no data column in {self._title}")
        self._ctx.click_point((int(x), match.click_point[1]), double=True)
        try:
            self._ctx.session.wait_for_dialog_closed(self._title, timeout=3)
        except WaitTimeout:
            self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "ok")))
            self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)

    def cancel(self) -> None:
        self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "cancel")))
        self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)
