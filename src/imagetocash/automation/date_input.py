"""Entering a date into a Nebula CDateTime field (Fakturama's date widgets), by keyboard only.

Found live:
- UIA SetValue only changes the text; the widget reverts on focus loss.
- Entering the field by Tab from the control before it selects its FIRST part (the month in en_US).
- Typed digits fill the selected part and move on by themselves when it is complete
  (2 digits for month/day, 4 for the year).
So: focus the preceding control, Tab in, confirm through UIA that the date field now has the
keyboard focus (never type blind), type the digits in display order, Tab out, verify.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from pywinauto import keyboard
from pywinauto.uia_defines import IUIA

from imagetocash.automation.input import read_value
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_LENIENT = re.compile(r"([A-Za-z]{3})\w*\s+(\d{1,2}),\s*(\d{1,4})")
_PART_CODES = {"month": ("%b", "%B", "%m"), "day": ("%d", "%e"), "year": ("%Y", "%y")}
KEY_PAUSE = 0.1  # measured: faster bursts lose digits in CDateTime


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


def typed_digits(target: date, display_format: str) -> str:
    """Digits in the order the field shows its parts: '%b %d, %Y' + 2026-07-14 -> '07142026'."""
    positions = {
        part: min((display_format.find(code) for code in codes if code in display_format), default=99)
        for part, codes in _PART_CODES.items()
    }
    digits = {"month": f"{target.month:02d}", "day": f"{target.day:02d}", "year": f"{target.year:04d}"}
    return "".join(digits[part] for part in sorted(positions, key=positions.__getitem__))


def has_keyboard_focus(element: Any) -> bool:
    try:
        focused = IUIA().iuia.GetFocusedElement()
        return bool(IUIA().iuia.CompareElements(focused, element.element_info.element))
    except Exception:
        return False


def set_cdatetime(
    element: Any,
    target: date,
    *,
    enter_from: Any,
    parse_format: str,
    commit: Callable[[], None],
    spec_step: str,
    field_name: str,
) -> None:
    text = typed_digits(target, parse_format)
    shown = ""
    # Twice at most: a day the previous year did not have (Feb 29) is accepted on the second pass,
    # once the year is already right.
    for _ in range(2):
        enter_from.set_focus()
        keyboard.send_keys("{TAB}")
        try:
            wait_until(lambda: has_keyboard_focus(element), timeout=2, what=f"{field_name} to receive focus")
        except WaitTimeout as error:
            raise ManualReviewRequired(
                spec_step, ReviewReason.UI_ELEMENT_NOT_FOUND, f"{field_name}: Tab did not reach the date field"
            ) from error
        keyboard.send_keys(text, pause=KEY_PAUSE)
        commit()  # move focus away so the widget commits its value
        time.sleep(0.1)
        shown = read_value(element)
        if _parse(shown, parse_format) == target:
            return
    raise ManualReviewRequired(
        spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: wanted {target}, field shows {shown!r}"
    )
