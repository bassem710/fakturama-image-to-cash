"""Read a custom-drawn table (NatTable) exactly, without OCR and without coordinates.

Found live: NatTable's default key bindings copy the selected cells as tab-separated text
(Ctrl+A selects all, Ctrl+C copies). Values are the raw model values, in display column order,
without a header row; VAT 19% comes back as 0.19 and empty cells as 'null'.
The user's clipboard text is restored afterwards.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import win32clipboard
from pywinauto import keyboard

_SENTINEL = "\x00imagetocash-empty\x00"


def _get_text() -> str | None:
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            return str(win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT))
        return None
    finally:
        win32clipboard.CloseClipboard()


def _set_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def parse_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip():
            rows.append(["" if cell.strip() == "null" else cell.strip() for cell in line.split("\t")])
    return rows


def copy_table(table: Any, timeout: float = 1.5) -> list[list[str]] | None:
    """Rows of `table` via Ctrl+A / Ctrl+C. None when nothing was copied (empty table, or a widget
    without the binding); the caller then uses its fallback."""
    previous: str | None = None
    with contextlib.suppress(Exception):
        previous = _get_text()
    try:
        _set_text(_SENTINEL)
        table.set_focus()
        keyboard.send_keys("^a^c", pause=0.02)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = None
            with contextlib.suppress(Exception):  # the clipboard may be busy for a moment
                text = _get_text()
            if text is not None and text != _SENTINEL:
                return parse_rows(text)
            time.sleep(0.05)
        return None
    finally:
        with contextlib.suppress(Exception):
            if previous is not None:
                _set_text(previous)
