"""Read a custom-drawn grid (e.g. NatTable) with OCR, inside the rectangle UIA gives for it.

Columns come from the header row: header words closer than `header_gap` px are one column title
("First Name"). A data word belongs to the column whose left edge is the closest one at or left
of the word (left-aligned cells). Every row keeps the screen point of its first word, so a row
can be clicked at a position measured at runtime, never a hardcoded coordinate.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass, field

from PIL import Image

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


def find_header_row(rows: list[list[OcrWord]], expected_headers: Sequence[str], header_gap: float = 14.0) -> int:
    wanted = {normalize_text(h) for h in expected_headers}
    for index, row in enumerate(rows):
        texts = {normalize_text(w.text) for w in row} | {normalize_text(t) for t, _ in _merge_header(row, header_gap)}
        if texts & wanted:
            return index
    return 0


def find_column_separators(
    image: Image.Image,
    rect: ScreenRect,
    band_top: float,
    band_bottom: float,
    min_contrast: int = 12,
    coverage: float = 0.85,
) -> list[float]:
    """Screen x of the vertical grid lines inside the header band: pixel columns darker than the
    band's background for (almost) its full height. Text strokes never span the whole band."""
    gray = image.convert("L")
    width, data = gray.width, gray.tobytes()  # one byte per pixel, row-major
    top, bottom = max(0, int(band_top - rect.top)), min(gray.height, int(band_bottom - rect.top))
    if bottom - top < 4:
        return []
    band = sorted(data[y * width + x] for x in range(0, width, 3) for y in range(top, bottom))
    background = band[len(band) // 2]
    needed = coverage * (bottom - top)
    dark = [
        sum(1 for y in range(top, bottom) if data[y * width + x] < background - min_contrast) >= needed
        for x in range(width)
    ]
    separators: list[float] = []
    run_start: int | None = None
    for x, is_dark in enumerate([*dark, False]):
        if is_dark and run_start is None:
            run_start = x
        elif not is_dark and run_start is not None:
            if x - run_start <= 4:  # thin lines only, not dark blocks
                separators.append(rect.left + (run_start + x - 1) / 2)
            run_start = None
    return separators


def build_table(
    words: list[OcrWord],
    expected_headers: Sequence[str] = (),
    separators: Sequence[float] = (),
    header_gap: float = 14.0,
    row_tolerance: float = 6.0,
    slack: float = 8.0,
) -> OcrTable:
    """With `separators` (grid lines), a word belongs to the column interval containing its centre,
    which works for left-aligned AND centred headers. Without them, fall back to header left edges."""
    rows = group_into_rows(words, row_tolerance)
    if not rows:
        return OcrTable(columns=())
    header_index = find_header_row(rows, expected_headers, header_gap) if expected_headers else 0
    header, body = rows[header_index], rows[header_index + 1 :]

    if separators:
        bounds = sorted(separators)

        def interval(word: OcrWord) -> int:
            return bisect.bisect(bounds, (word.left + word.right) / 2)

        titles: dict[int, list[OcrWord]] = {}
        for word in header:
            titles.setdefault(interval(word), []).append(word)
        columns = [
            (" ".join(w.text for w in ws), bounds[i - 1] if i > 0 else min(w.left for w in ws))
            for i, ws in sorted(titles.items())
        ]
        title_of = {i: " ".join(w.text for w in ws) for i, ws in titles.items()}
        table_rows = []
        for row in body:
            cells: dict[str, list[str]] = {title: [] for title, _ in columns}
            for word in row:
                if (column := title_of.get(interval(word))) is not None:
                    cells[column].append(word.text)
            table_rows.append(OcrTableRow({k: " ".join(v) for k, v in cells.items()}, click_point=row[0].center))
        return OcrTable(columns=tuple(columns), rows=tuple(table_rows))

    columns = _merge_header(header, header_gap)
    lefts = [left for _, left in columns]
    table_rows = []
    for row in body:
        cells = {title: [] for title, _ in columns}
        for word in row:
            candidates = [i for i, left in enumerate(lefts) if left - slack <= word.left]
            cells[columns[candidates[-1] if candidates else 0][0]].append(word.text)
        table_rows.append(OcrTableRow({k: " ".join(v) for k, v in cells.items()}, click_point=row[0].center))
    return OcrTable(columns=tuple(columns), rows=tuple(table_rows))


class OcrTableReader:
    def __init__(self, ocr: WindowsScreenOcr) -> None:
        self._ocr = ocr

    def read(self, rect: ScreenRect, expected_headers: Sequence[str] = ()) -> OcrTable:
        image = self._ocr.capture(rect)
        words = self._ocr.read_image(image, rect)
        rows = group_into_rows(words)
        separators: list[float] = []
        if rows:
            header = rows[find_header_row(rows, expected_headers)]
            top, bottom = min(w.top for w in header), max(w.bottom for w in header)
            separators = find_column_separators(image, rect, top - 3, bottom + 3)
        return build_table(words, expected_headers, separators)
