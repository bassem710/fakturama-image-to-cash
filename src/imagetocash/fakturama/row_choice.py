"""THE ONE pointer exception (decided with the user): opening/choosing a row in a custom-drawn list.

Found live: 'Select the address' / 'Select a product' apply a row only on a mouse double-click on
that row; keyboard selection + OK applies nothing (6 variants tested). Data views (VATs) open a record
only on a double-click too. Rows are not UIA elements.
So the matched row is double-clicked at a point computed at run time RELATIVE TO THE LIST ELEMENT's
own UIA rectangle: the row is found by its CONTENT in an OCR read of that list (never by its index in
the clipboard copy, which can hold off-screen or blank rows), the column from its header. No fixed
numbers, so it works on any screen size or scaling. Nothing else in src/ may use the pointer
(tests/unit/test_no_coordinates.py allows only this module).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from imagetocash.automation.ocr_table import OcrTableReader, OcrTableRow
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.domain.matching import normalize_ocr_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import ParseError, parse_amount

_ELLIPSIS = re.compile(r"(?:\s*\.){2,}\s*$|\s*…\s*$")
_NUMERIC = re.compile(r"[\s$€%0-9.,/-]*[0-9][\s$€%0-9.,/-]*")  # an amount or percent, OCR '0/0' included


def same_cell(shown: str, wanted: str) -> bool:
    """An OCR'd cell shows `wanted`: equal text (OCR-folded) or, when BOTH are plain amounts or
    percentages, the same number ('19.00 %' / '19%'). Codes like 'A-100' never compare as numbers. A
    cell the column truncated ('Northstar Offic...') matches by its visible prefix (3+ characters)."""
    seen, expected = normalize_ocr_text(shown), normalize_ocr_text(wanted)
    if seen == expected:
        return True
    if truncated := _ELLIPSIS.search(seen):  # OCR reads the ellipsis as '...', '..', '…' or '. . .'
        prefix = seen[: truncated.start()].strip()
        return len(prefix) >= 3 and expected.startswith(prefix)
    if not (_NUMERIC.fullmatch(shown) and _NUMERIC.fullmatch(wanted)):
        return False
    try:
        return parse_amount(shown) == parse_amount(wanted)
    except ParseError:
        return False


def rows_showing(
    rows: Sequence[OcrTableRow], titles: Mapping[str, str], wanted: Mapping[str, str], pick_fields: Sequence[str]
) -> list[OcrTableRow]:
    """OCR rows whose `pick_fields` cells (field -> header title in `titles`) show the wanted values."""
    return [r for r in rows if all(same_cell(r.cells.get(titles[f], ""), wanted.get(f, "")) for f in pick_fields)]


def open_row_with_pointer(
    table: Any,
    reader: OcrTableReader,
    columns: Mapping[str, str],
    wanted: Mapping[str, str],
    pick_fields: Sequence[str],
) -> None:
    """Double-click the ONE visible row of `table` whose `pick_fields` show `wanted`'s values.
    `columns` maps header titles to fields. Zero or several such rows -> manual review."""
    titles = {field: title for title, field in columns.items()}
    rect = ScreenRect.of(table)
    ocr = reader.read(rect, expected_headers=tuple(columns))
    matches = rows_showing(ocr.rows, titles, wanted, pick_fields)
    x = next((x for f in pick_fields if (x := ocr.column_center_x(titles[f])) is not None), None)
    if x is None or len(matches) != 1:
        shown = {f: wanted.get(f, "") for f in pick_fields}
        raise ManualReviewRequired(
            "-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"{len(matches)} visible row(s) show {shown}; need exactly one"
        )
    table.double_click_input(coords=(int(x - rect.left), int(matches[0].middle_y - rect.top)))  # element-relative
