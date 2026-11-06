"""Setting a Nebula CDateTime field (Fakturama's date widgets).

Discovery showed the widget ignores UIA SetValue (it reverts on focus loss) and edits ONE field at a
time: Right moves to the next field (wrapping), Up/Down step the selected field, digits overwrite it.
Which field is selected after focusing is not fixed, so we probe it: press Up, see which part of the
date moved, press Down to undo. Then every part is reached with Right and set deterministically.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.input import read_value
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

FIELD_ORDER = ("month", "day", "year")  # en_US "MMM d, yyyy": Right cycles month -> day -> year -> month
KEY_PAUSE = 0.05


_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_LENIENT = re.compile(r"([A-Za-z]{3})\w*\s+(\d{1,2}),\s*(\d{1,4})")


def _parse(text: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), fmt).date()
    except ValueError:
        pass
    match = _LENIENT.fullmatch(text.strip())  # e.g. a half-edited "Dec 20, 27"
    if match and match.group(1).lower() in _MONTHS:
        try:
            return date(int(match.group(3)), _MONTHS.index(match.group(1).lower()) + 1, int(match.group(2)))
        except ValueError:
            return None
    return None


def _changed_part(before: date, after: date) -> str:
    if before.year != after.year:
        return "year"
    if before.month != after.month:
        return "month"
    return "day"


def set_cdatetime(
    element: Any,
    target: date,
    *,
    parse_format: str,
    commit: Callable[[], None],
    spec_step: str,
    field_name: str,
) -> None:
    def current() -> date:
        value = _parse(read_value(element), parse_format)
        if value is None:
            raise ManualReviewRequired(
                spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: cannot read {read_value(element)!r}"
            )
        return value

    def send(keys: str) -> None:
        keyboard.send_keys(keys, pause=KEY_PAUSE)
        time.sleep(0.1)

    def selected_part() -> str:
        """Probe: Up then Down; whichever part moved is the selected field."""
        before = current()
        send("{UP}")
        moved = _changed_part(before, current())
        send("{DOWN}")
        return moved

    element.set_focus()
    # Digits overwrite the selected field and auto-advance when it is complete, so each part is
    # re-located by probing instead of assuming where the cursor ended up.
    # Year, then month, then day: the day is set last so it is never clamped by a shorter month/year.
    for part, digits in (
        ("year", f"{target.year:04d}"),
        ("month", f"{target.month:02d}"),
        ("day", f"{target.day:02d}"),
    ):
        steps = (FIELD_ORDER.index(part) - FIELD_ORDER.index(selected_part())) % len(FIELD_ORDER)
        send("{RIGHT}" * steps + digits if steps else digits)

    commit()  # move focus away so the widget commits its value
    time.sleep(0.3)
    if current() != target:
        raise ManualReviewRequired(
            spec_step,
            ReviewReason.VALUE_MISMATCH,
            f"{field_name}: wanted {target}, field shows {read_value(element)!r}",
        )
