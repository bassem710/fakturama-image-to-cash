"""Read a custom-drawn table (NatTable) exactly, without OCR and without coordinates.

Found live: NatTable's default key bindings copy the selected cells as tab-separated text
(Ctrl+A selects all, Ctrl+C copies). Values are the raw model values, in display column order,
without a header row; VAT 19% comes back as 0.19 and empty cells as 'null'.
The user's clipboard text is restored afterwards.
"""

from __future__ import annotations

import contextlib
from typing import Any

import win32clipboard
from pywinauto import keyboard

from imagetocash.automation.focus import focus
from imagetocash.automation.waiting import WaitTimeout, wait_until

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
        focus(table)  # a lost Ctrl+A copies only the selected row: confirm focus first
        keyboard.send_keys("^a^c", pause=0.03)

        def copied() -> str | None:
            text = _get_text()  # may raise while the clipboard is busy: wait_until retries
            return text if text is not None and text != _SENTINEL else None

        try:
            return parse_rows(wait_until(copied, timeout=timeout, what="the table copy", interval=0.05))
        except WaitTimeout:
            return None
    finally:
        with contextlib.suppress(Exception):
            if previous is not None:
                _set_text(previous)
