"""Read a custom-drawn grid (e.g. NatTable) with OCR, inside the rectangle UIA gives for it.

Columns come from the header row: header words closer than `header_gap` px are one column title
("First Name"). A data word belongs to the column whose left edge is the closest one at or left
of the word (left-aligned cells). Every row keeps the screen point of its first word, so a row
can be clicked at a position measured at runtime, never a hardcoded coordinate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from imagetocash.automation.screen_ocr import OcrWord, ScreenRect, WindowsScreenOcr, group_into_rows
from imagetocash.domain.matching import normalize_text


@dataclass(frozen=True)
class OcrTableRow:
    cells: dict[str, str]
    click_point: tuple[int, int]

    def __hash__(self) -> int:
        return hash((tuple(sorted(self.cells.items())), self.click_point))


@dataclass(frozen=True)
class OcrTable:
    columns: tuple[tuple[str, float], ...]  # (title, left edge)
    rows: tuple[OcrTableRow, ...] = field(default_factory=tuple)

    def column_center_x(self, title: str) -> float | None:
        for index, (name, left) in enumerate(self.columns):
            if normalize_text(name) == normalize_text(title):
                right = self.columns[index + 1][1] if index + 1 < len(self.columns) else left + 120
                return (left + right) / 2
        return None


def _merge_header(words: list[OcrWord], header_gap: float) -> list[tuple[str, float]]:
    columns: list[tuple[str, float, float]] = []  # title, left, right
    for word in words:
        if columns and word.left - columns[-1][2] <= header_gap:
            title, left, _ = columns[-1]
            columns[-1] = (f"{title} {word.text}", left, word.right)
        else:
            columns.append((word.text, word.left, word.right))
    return [(title, left) for title, left, _ in columns]


def build_table(
    words: list[OcrWord],
    expected_headers: Sequence[str] = (),
    header_gap: float = 14.0,
    row_tolerance: float = 6.0,
    slack: float = 8.0,
) -> OcrTable:
    rows = group_into_rows(words, row_tolerance)
    if not rows:
        return OcrTable(columns=())
    wanted = {normalize_text(h) for h in expected_headers}
    header_index = 0
    if wanted:
        for index, row in enumerate(rows):
            texts = {normalize_text(w.text) for w in row} | {
                normalize_text(t) for t, _ in _merge_header(row, header_gap)
            }
            if texts & wanted:
                header_index = index
                break
    columns = _merge_header(rows[header_index], header_gap)
    lefts = [left for _, left in columns]

    table_rows: list[OcrTableRow] = []
    for row in rows[header_index + 1 :]:
        cells: dict[str, list[str]] = {title: [] for title, _ in columns}
        for word in row:
            candidates = [i for i, left in enumerate(lefts) if left - slack <= word.left]
            column = columns[candidates[-1] if candidates else 0][0]
            cells[column].append(word.text)
        table_rows.append(OcrTableRow(cells={k: " ".join(v) for k, v in cells.items()}, click_point=row[0].center))
    return OcrTable(columns=tuple(columns), rows=tuple(table_rows))


class OcrTableReader:
    def __init__(self, ocr: WindowsScreenOcr) -> None:
        self._ocr = ocr

    def read(self, rect: ScreenRect, expected_headers: Sequence[str] = ()) -> OcrTable:
        return build_table(self._ocr.read_words(rect), expected_headers)
