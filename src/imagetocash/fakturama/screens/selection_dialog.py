"""'Select the address' / 'Select a product' dialogs (spec 2.2-2.3, 2.12, 3.3, 3.12).

No coordinates: the search box is set through UIA (read back), rows are read from the table by
clipboard (OCR only as fallback), and the matched row is double-clicked inside the list element
(the one pointer exception, see fakturama/row_choice.py); OK through Invoke if the dialog stays.
The caller verifies the effect (addresses populated / a new Items line), as the spec requires.

'Select a product' filters on every keystroke over all columns and applies its row by itself as soon
as exactly ONE is left. Typing would apply whatever a prefix matches first, so the search text is set
in ONE modify event (ValuePattern.SetValue; a filter box has no data binding, unlike editor fields),
and a dialog that closes on its own is reported as `auto_applied` for the caller to verify.
"""

from __future__ import annotations

import ctypes
from collections.abc import Mapping, Sequence
from typing import Any

from imagetocash.automation.input import read_value
from imagetocash.automation.locators import locate
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.row_choice import choose_row_with_pointer
from imagetocash.fakturama.screen_context import ScreenContext

S = "selection_dialogs"
AUTO_APPLY_GRACE_SECONDS = 0.6  # the dialog closes right after its filter leaves one row
DOUBLE_CLICK_CLOSE_SECONDS = 3.0
_user32 = ctypes.windll.user32


class SelectionDialogScreen:
    def __init__(
        self, ctx: ScreenContext, dialog: Any, title: str, columns: Mapping[str, str], order: Sequence[str]
    ) -> None:
        self._ctx, self._dialog, self._title = ctx, dialog, title
        self._columns, self._order = columns, order
        self._rows: list[dict[str, str]] = []
        self.auto_applied = False  # Fakturama applied its only filter hit and closed the dialog

    @classmethod
    def open(cls, ctx: ScreenContext, kind: str) -> SelectionDialogScreen:
        """Wait for the dialog `kind` ('address' / 'product') that the caller's click just opened."""
        title = str(ctx.selectors.value(S, f"{kind}_title"))
        dialog = ctx.session.wait_for_dialog(title, ctx.settings.timeouts.dialog)
        columns = dict(ctx.selectors.value(S, f"{kind}_columns"))
        return cls(ctx, dialog, title, columns, list(ctx.selectors.value(S, f"{kind}_order")))

    def search(self, text: str) -> list[dict[str, str]]:
        search_box = locate(self._dialog, self._ctx.selectors.locator(S, "search"))
        search_box.iface_value.SetValue(text)  # one modify event: no prefix can auto-apply a wrong row
        try:
            wait_until(lambda: not self._is_open(), timeout=AUTO_APPLY_GRACE_SECONDS, what="auto-apply", interval=0.05)
            self.auto_applied = True
            self._ctx.invalidate()
            return []
        except WaitTimeout:
            pass  # still open: read the filtered list
        shown = read_value(search_box)
        if shown != text:
            raise ManualReviewRequired(
                "-", ReviewReason.VALUE_MISMATCH, f"{self._title} search: set {text!r}, field shows {shown!r}"
            )
        self._rows = self._ctx.lists.read(self._table(), self._columns, self._order)
        return [dict(record) for record in self._rows]

    def choose(self, row: Mapping[str, str]) -> None:
        self._require_open()
        index = next((i for i, record in enumerate(self._rows) if record == dict(row)), None)
        if index is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"row vanished from {self._title}")
        choose_row_with_pointer(self._table(), self._ctx.ocr, index, tuple(self._columns))  # double-click only
        try:
            self._ctx.session.wait_for_dialog_closed(self._title, timeout=DOUBLE_CLICK_CLOSE_SECONDS)
        except WaitTimeout:
            get_logger().warning(f"'{self._title}' stayed open after the double-click; pressing OK")
            self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "ok")))
            self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)
        self._ctx.invalidate()

    def cancel(self) -> None:
        self._require_open()
        self._ctx.press(locate(self._dialog, self._ctx.selectors.locator(S, "cancel")))
        self._ctx.session.wait_for_dialog_closed(self._title, self._ctx.settings.timeouts.dialog)

    def _table(self) -> Any:
        return self._ctx.lists.table_in(self._dialog)

    def _is_open(self) -> bool:
        """Two Win32 calls on the dialog's handle (enumerating all windows costs far more)."""
        handle = int(self._dialog.handle or 0)
        if not handle:  # no native window: fall back to the title
            return any(d.element_info.name == self._title for d in self._ctx.session.dialogs())
        return bool(_user32.IsWindow(handle) and _user32.IsWindowVisible(handle))

    def _require_open(self) -> None:
        if self.auto_applied:
            raise ManualReviewRequired(
                "-", ReviewReason.VALUE_MISMATCH, f"{self._title} applied a record by itself; nothing to choose"
            )
