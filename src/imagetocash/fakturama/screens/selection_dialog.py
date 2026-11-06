"""'Select the address' / 'Select a product' dialogs (spec 2.2-2.3, 2.12, 3.3, 3.12).

No coordinates: the search box is set through UIA (read back), rows are read from the table by
clipboard (OCR only as fallback), the matched row is selected with the keyboard (Ctrl+Home, then
Down to its index) and OK is pressed through its Invoke pattern. The caller verifies the effect
(addresses populated / a new Items line), as the spec requires.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import set_and_verify
from imagetocash.automation.locators import locate
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext

S = "selection_dialogs"


class SelectionDialogScreen:
    def __init__(
        self, ctx: ScreenContext, dialog: Any, title: str, columns: Mapping[str, str], order: Sequence[str]
    ) -> None:
        self._ctx, self._dialog, self._title = ctx, dialog, title
        self._columns, self._order = columns, order
        self._rows: list[dict[str, str]] = []

    def search(self, text: str) -> list[dict[str, str]]:
        search_box = locate(self._dialog, self._ctx.selectors.locator(S, "search"))
        set_and_verify(search_box, text, spec_step="-", field_name=f"{self._title} search")
        self._rows = self._ctx.read_table_rows(self._table(), self._columns, self._order)
        return [dict(record) for record in self._rows]

    def choose(self, row: Mapping[str, str]) -> None:
        index = next((i for i, record in enumerate(self._rows) if record == dict(row)), None)
        if index is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"row vanished from {self._title}")
        self._table().set_focus()
        keyboard.send_keys("^{HOME}" + "{DOWN}" * index, pause=0.03)  # select the row by keyboard
        self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "ok")))
        self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)

    def cancel(self) -> None:
        self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "cancel")))
        self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)

    def _table(self) -> Any:
        return self._ctx.table_in(self._dialog)
