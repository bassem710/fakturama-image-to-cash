"""Read a custom-drawn grid (e.g. NatTable) with OCR, inside the rectangle UIA gives for it.

Columns come from the header row: header words closer than `header_gap` px are one column title
("First Name"). A data word belongs to the column whose left edge is the closest one at or left
of the word (left-aligned cells). OCR is a read-only fallback; nothing is ever clicked at a measured position.
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
    middle_y: float = 0.0  # screen y of the row's text (used only by fakturama/row_choice.py)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.cells.items())))


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


def _is_grid_glyph(text: str) -> bool:
    """Header tokens that are OCR'd grid lines: punctuation or a single stroke letter."""
    return _is_punctuation(text) or text in {"I", "l", "|", "!"}


def _is_punctuation(text: str) -> bool:
    """OCR reads header grid lines as stray ',', '|', '.' tokens: they are column boundaries, not titles."""
    return not any(ch.isalnum() for ch in text)


def _merge_header(words: list[OcrWord], header_gap: float) -> list[tuple[str, float]]:
    columns: list[tuple[str, float, float]] = []  # title, left, right
    split_next = False
    for word in words:
        if _is_punctuation(word.text):
            split_next = True
            continue
        if columns and not split_next and word.left - columns[-1][2] <= header_gap:
            title, left, _ = columns[-1]
            columns[-1] = (f"{title} {word.text}", left, word.right)
        else:
            columns.append((word.text, word.left, word.right))
        split_next = False
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
    """Screen x of the vertical grid lines inside the header band: pixel columns that differ from the
    band's background for (almost) its full height. Darker OR lighter: a focused list draws a dark
    header with light grid lines (seen live). Text strokes never span the whole band."""
    gray = image.convert("L")
    width, data = gray.width, gray.tobytes()  # one byte per pixel, row-major
    top, bottom = max(0, int(band_top - rect.top)), min(gray.height, int(band_bottom - rect.top))
    if bottom - top < 4:
        return []
    band = sorted(data[y * width + x] for x in range(0, width, 3) for y in range(top, bottom))
    background = band[len(band) // 2]
    needed = coverage * (bottom - top)
    dark = [
        sum(1 for y in range(top, bottom) if abs(data[y * width + x] - background) > min_contrast) >= needed
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
    # Grid lines OCR read as ',' / '|' / 'I' in the header are separators too, and a "separator"
    # inside a header word is a text stroke, not a grid line (seen on focused, dark headers).
    glyphs = [w for w in header if _is_grid_glyph(w.text)]
    titles_words = [w for w in header if not _is_grid_glyph(w.text)]
    candidates = [*separators, *((w.left + w.right) / 2 for w in glyphs)]
    candidates = [x for x in candidates if not any(w.left + 2 < x < w.right - 2 for w in titles_words)]
    # With real grid lines found, also split around every expected title (a missed line merges two
    # titles), unless the cut would go through a longer expected title ("First Name" stays whole).
    if candidates:
        known = {normalize_text(h) for h in expected_headers}
        texts = [w.text for w in titles_words]
        spans = [
            (i, j)
            for i in range(len(texts))
            for j in range(i + 1, len(texts) + 1)
            if normalize_text(" ".join(texts[i:j])) in known
        ]
        inside = {k for i, j in spans if j - i > 1 for k in range(i + 1, j)}
        lines = sorted(candidates)
        for i, j in spans:
            for cut in (i, j):
                if not 0 < cut < len(texts) or cut in inside:
                    continue
                before, after = titles_words[cut - 1], titles_words[cut]
                if bisect.bisect(lines, before.right) == bisect.bisect(lines, after.left):  # same interval
                    candidates.append((before.right + after.left) / 2)
    merged: list[float] = []
    for x in sorted(candidates):
        if not merged or x - merged[-1] > 6:
            merged.append(x)
    separators = merged

    if separators:
        bounds = sorted(separators)

        def interval(word: OcrWord) -> int:
            return bisect.bisect(bounds, (word.left + word.right) / 2)

        titles: dict[int, list[OcrWord]] = {}
        for word in titles_words:
            titles.setdefault(interval(word), []).append(word)
        title_of = {i: " ".join(w.text for w in ws) for i, ws in titles.items()}
        title_of |= _titles_by_position(title_of, len(bounds), expected_headers)
        columns = [
            (title, bounds[i - 1] if i > 0 else min(w.left for w in titles[i])) for i, title in sorted(title_of.items())
        ]
        table_rows = []
        for row in body:
            cells: dict[str, list[str]] = {title: [] for title, _ in columns}
            for word in row:
                if (column := title_of.get(interval(word))) is not None:
                    cells[column].append(word.text)
            table_rows.append(OcrTableRow({k: " ".join(v) for k, v in cells.items()}, middle_y=row[0].middle_y))
        return OcrTable(columns=tuple(columns), rows=tuple(table_rows))

    columns = _merge_header(header, header_gap)
    lefts = [left for _, left in columns]
    table_rows = []
    for row in body:
        cells = {title: [] for title, _ in columns}
        for word in row:
            starts = [i for i, left in enumerate(lefts) if left - slack <= word.left]
            cells[columns[starts[-1] if starts else 0][0]].append(word.text)
        table_rows.append(OcrTableRow({k: " ".join(v) for k, v in cells.items()}, middle_y=row[0].middle_y))
    return OcrTable(columns=tuple(columns), rows=tuple(table_rows))


def _alnum_count(words: Sequence[OcrWord]) -> int:
    return sum(ch.isalnum() for w in words for ch in w.text)


def _titles_by_position(
    title_of: dict[int, str], interval_count: int, expected_headers: Sequence[str]
) -> dict[int, str]:
    """Name grid intervals whose title OCR missed, so their cells are not dropped: an untitled interval
    between two read titles gets the expected title at the same offset, only when the read titles are
    exactly as far apart in `expected_headers` as on screen (no unexpected column in between)."""
    order = [normalize_text(h) for h in expected_headers]
    found: dict[int, str] = {}
    titled = sorted(title_of)
    for i in range(1, interval_count):  # interval 0 lies left of the first grid line (row header)
        if i in title_of:
            continue
        left = max((t for t in titled if t < i), default=None)
        right = min((t for t in titled if t > i), default=None)
        if left is None or right is None:
            continue
        a, b = normalize_text(title_of[left]), normalize_text(title_of[right])
        if a not in order or b not in order or order.index(b) - order.index(a) != right - left:
            continue
        found[i] = expected_headers[order.index(a) + (i - left)]
    return found


def selection_bands(image: Image.Image, rect: ScreenRect, min_share: float = 0.25) -> list[tuple[float, float]]:
    """Screen y ranges of rows painted in the selection blue (strong blue, little red)."""
    rgb = image.convert("RGB")
    width, height, data = rgb.width, rgb.height, rgb.tobytes()
    blue_rows = []
    for y in range(height):
        hits = 0
        for x in range(0, width, 4):
            i = (y * width + x) * 3
            if data[i + 2] > 150 and data[i + 2] - data[i] > 80:
                hits += 1
        blue_rows.append(hits > min_share * (width / 4))
    bands: list[tuple[float, float]] = []
    start: int | None = None
    for y, is_blue in enumerate([*blue_rows, False]):
        if is_blue and start is None:
            start = y
        elif not is_blue and start is not None:
            bands.append((rect.top + start, rect.top + y - 1))
            start = None
    return bands


def invert_bands(image: Image.Image, rect: ScreenRect, bands: Sequence[tuple[float, float]]) -> Image.Image:
    """Grayscale copy with the selection bands inverted, so their text is dark on light."""
    gray = image.convert("L")
    width, out = gray.width, bytearray(gray.tobytes())
    for top, bottom in bands:
        for y in range(int(top - rect.top), int(bottom - rect.top) + 1):
            for x in range(width):
                out[y * width + x] = 255 - out[y * width + x]
    return Image.frombytes("L", gray.size, bytes(out)).convert("RGB")


class OcrTableReader:
    def __init__(self, ocr: WindowsScreenOcr) -> None:
        self._ocr = ocr

    def has_data_rows(self, rect: ScreenRect, expected_headers: Sequence[str] = ()) -> bool:
        """Any text below the header row? (One OCR pass, read-only.)"""
        rows = group_into_rows(self._ocr.read_words(rect))
        if not rows:
            return False
        header = find_header_row(rows, expected_headers) if expected_headers else 0
        return len(rows) > header + 1

    def read(self, rect: ScreenRect, expected_headers: Sequence[str] = ()) -> OcrTable:
        image = self._ocr.capture(rect)
        words = self._ocr.read_image(image, rect)
        bands = selection_bands(image, rect)
        if bands:  # selected rows: white text on blue often reads badly; re-read those bands inverted
            inverted = self._ocr.read_image(invert_bands(image, rect, bands), rect)
            for top, bottom in bands:  # per band, keep the read that recovered more characters (live
                # 2026-11-08: plain 'CHR-ERG-OI', inverted 'CHR-ERG-O' on the solid-blue product row)
                plain = [w for w in words if top <= w.middle_y <= bottom]
                flipped = [w for w in inverted if top <= w.middle_y <= bottom]
                if _alnum_count(flipped) > _alnum_count(plain):
                    words = [w for w in words if not top <= w.middle_y <= bottom] + flipped
        rows = group_into_rows(words)
        separators: list[float] = []
        if rows:
            header = rows[find_header_row(rows, expected_headers)]
            top, bottom = min(w.top for w in header), max(w.bottom for w in header)
            separators = find_column_separators(image, rect, top - 3, bottom + 3)
            words = self._with_header_reread(image, rect, words, top - 3, bottom + 3)
        return build_table(words, expected_headers, separators)

    def _with_header_reread(
        self, image: Image.Image, rect: ScreenRect, words: list[OcrWord], band_top: float, band_bottom: float
    ) -> list[OcrWord]:
        """OCR the header band again on its own. Read together with the rows, Windows OCR drops short
        titles on the dark focused header (live, 2560x1440 @100%: 'ZIP' missing, 'address' -> 'ddress');
        cropped alone it reads them. Keeps the first read if the re-read finds fewer header words."""
        y0, y1 = max(0, int(band_top - rect.top)), min(image.height, int(band_bottom - rect.top) + 1)
        if y1 - y0 < 4:
            return words
        band = ScreenRect(rect.left, rect.top + y0, rect.right, rect.top + y1)
        reread = self._ocr.read_image(image.crop((0, y0, image.width, y1)), band)
        old = [w for w in words if band_top <= w.middle_y <= band_bottom]
        if len(reread) <= len(old):
            return words
        return [w for w in words if not band_top <= w.middle_y <= band_bottom] + reread
