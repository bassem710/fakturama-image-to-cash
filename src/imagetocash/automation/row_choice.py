"""THE ONE pointer exception (decided with the user): choosing a row in Fakturama's selection dialogs.

Found live: 'Select the address' / 'Select a product' apply a row only on a mouse double-click on
that row; keyboard selection + OK applies nothing (6 variants tested). Rows are not UIA elements.
So the matched row is double-clicked at a point computed at run time RELATIVE TO THE LIST ELEMENT's
own UIA rectangle: the row's height from OCR of that list, the column from its header. No fixed
numbers, so it works on any screen size or scaling. Nothing else in src/ may use the pointer
(tests/unit/test_no_coordinates.py allows only this module).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from imagetocash.automation.ocr_table import OcrTableReader
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.domain.review import ManualReviewRequired, ReviewReason


def choose_row_with_pointer(table: Any, reader: OcrTableReader, row_index: int, headers: Sequence[str]) -> None:
    rect = ScreenRect.of(table)
    ocr = reader.read(rect, expected_headers=tuple(headers))
    x = next((x for title in headers if (x := ocr.column_center_x(title)) is not None), None)
    if x is None or row_index >= len(ocr.rows):
        raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "row to choose not visible in the list")
    y = ocr.rows[row_index].middle_y
    table.double_click_input(coords=(int(x - rect.left), int(y - rect.top)))  # element-relative point
