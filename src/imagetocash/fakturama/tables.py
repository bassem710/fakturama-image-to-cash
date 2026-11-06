"""Reading Fakturama's custom-drawn lists (Nebula NatTable): clipboard copy first, OCR as fallback.

A NatTable is opaque to UIA (no rows or cells), but its default key bindings copy the selected cells
as tab-separated raw model values in display column order (Ctrl+A, Ctrl+C). That is exact and fast.
When the copy has an unexpected shape, the list is read with OCR inside the table's UIA rectangle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from imagetocash.automation.clipboard_table import copy_table
from imagetocash.automation.locators import largest_leaf_pane
from imagetocash.automation.ocr_table import OcrTable
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.automation.waiting import wait_until, wait_until_stable
from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.values import fraction_to_percent

if TYPE_CHECKING:
    from imagetocash.fakturama.screen_context import ScreenContext

Record = dict[str, str]


class ListReader:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx

    @staticmethod
    def table_in(scope: Any) -> Any:
        """The NatTable inside `scope`: in UIA, the biggest Pane whose only children are scrollbars."""
        table = largest_leaf_pane(scope)
        if table is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "no table pane found")
        return table

    def read(
        self,
        table: Any,
        columns: Mapping[str, str],
        order: Sequence[str],
        percent_fields: Sequence[str] = (),
        *,
        may_be_empty: bool = True,
    ) -> list[Record]:
        """Rows of a NatTable as records. `order` names the field of each copied column ('' skips one);
        `columns` maps header titles to fields for the OCR fallback. `percent_fields` hold model
        fractions ('0.19') and come back as '19%'.

        Ctrl+C on an EMPTY NatTable makes Fakturama show an error dialog, so a list that may be empty
        (a search result) gets a quick read-only OCR look first; `may_be_empty=False` (the Items grid
        once a line exists) skips that look."""
        if may_be_empty and not self._ctx.ocr.has_data_rows(ScreenRect.of(table), expected_headers=tuple(columns)):
            return []
        copied = copy_table(table)
        if copied is None and self._acknowledge_empty_copy_error():
            return []
        # Some lists copy hidden columns after the visible ones (Select the address): the configured
        # fields are the leading columns, extra trailing cells are ignored.
        if copied is not None and all(len(row) >= len(order) for row in copied):
            return [r for r in (_record(row, order, percent_fields) for row in copied) if any(r.values())]
        if copied:
            get_logger().warning(f"table copy had an unexpected shape ({len(copied[0])} cells), using OCR")
        return self._read_ocr(table, columns)

    def _acknowledge_empty_copy_error(self) -> bool:
        """A list can empty itself (a filter still applying) between the OCR look and Ctrl+C. Fakturama
        then shows its Internal Error dialog naming the empty copy. That exact error comes from our own
        copy and changes no data: acknowledge it, and the list is empty. Any other error stays."""
        ctx = self._ctx
        title = str(ctx.selectors.value("app", "internal_error_title"))
        marker = str(ctx.selectors.value("app", "empty_copy_error_marker"))
        ok = str(ctx.selectors.value("app", "error_ok"))
        dialog = next((d for d in ctx.session.dialogs() if d.element_info.name == title), None)
        if dialog is None:
            return False
        if marker not in " ".join(t.element_info.name for t in dialog.descendants(control_type="Text")):
            return False
        ctx.press(next(b for b in dialog.descendants(control_type="Button") if b.element_info.name == ok))
        wait_until(
            lambda: all(d.element_info.name != title for d in ctx.session.dialogs()),
            timeout=ctx.settings.timeouts.dialog,
            what="the copy error to close",
        )
        get_logger().info("empty table: acknowledged Fakturama's empty-copy error")
        return True

    def _read_ocr(self, table: Any, columns: Mapping[str, str]) -> list[Record]:
        last: list[OcrTable] = []

        def read() -> tuple[tuple[tuple[str, str], ...], ...]:
            last[:] = [self._ctx.ocr.read(ScreenRect.of(table), expected_headers=tuple(columns))]
            return tuple(tuple(sorted(r.cells.items())) for r in last[0].rows)

        wait_until_stable(read, timeout=self._ctx.settings.timeouts.list_stable, what="the list")
        records = []
        for row in last[0].rows:
            record = {
                field: next((v for k, v in row.cells.items() if normalize_text(k) == normalize_text(title)), "")
                for title, field in columns.items()
            }
            if any(record.values()):
                records.append(record)
        return records


def _record(row: Sequence[str], order: Sequence[str], percent_fields: Sequence[str]) -> Record:
    record = {field: cell for field, cell in zip(order, row[: len(order)], strict=True) if field}
    for field in percent_fields:
        if record.get(field):
            record[field] = fraction_to_percent(record[field])
    return record
