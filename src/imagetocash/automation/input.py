"""Typing and reading values through UIA, with read-back verification ("verify each step")."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pywinauto import keyboard

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

_SEND_KEYS_SPECIALS = set("+^%~(){}[]")


def escape_send_keys(text: str) -> str:
    """pywinauto send_keys treats + ^ % ~ ( ) { } [ ] as commands; brace them to type literally."""
    return "".join(f"{{{ch}}}" if ch in _SEND_KEYS_SPECIALS else ch for ch in text)


def read_value(element: Any) -> str:
    """UIA Value pattern first, element name as a fallback (static texts)."""
    try:
        return str(element.iface_value.CurrentValue or "")
    except Exception:
        return str(element.element_info.name or "")


def type_into(element: Any, text: str, commit_key: str = "{TAB}") -> None:
    """Focus, select all, type, commit. Typing (not ValuePattern.SetValue) fires SWT's own
    modify/verify listeners, so Fakturama recalculates exactly as for a human user."""
    element.set_focus()
    keyboard.send_keys("^a{DELETE}", pause=0.02)
    if text:
        keyboard.send_keys(escape_send_keys(text), with_spaces=True, pause=0.01)
    if commit_key:
        keyboard.send_keys(commit_key, pause=0.02)


def set_and_verify(
    element: Any,
    value: str,
    *,
    spec_step: str,
    field_name: str,
    normalize: Callable[[str], str] = normalize_text,
    reader: Callable[[Any], str] = read_value,
    attempts: int = 2,
) -> str:
    """Type `value`, read it back, retry once, then stop for manual review."""
    observed = ""
    for _ in range(attempts):
        type_into(element, value)
        observed = reader(element)
        if normalize(observed) == normalize(value):
            return observed
    raise ManualReviewRequired(
        spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: typed {value!r}, field shows {observed!r}"
    )


def select_combo_option(combo: Any, option: str, *, spec_step: str, field_name: str) -> None:
    """Select a ComboBox entry by its visible text and verify the selection."""
    if normalize_text(read_value(combo)) == normalize_text(option):
        return
    try:
        combo.select(option)
    except Exception:
        combo.set_focus()
        keyboard.send_keys(escape_send_keys(option) + "{ENTER}", with_spaces=True, pause=0.02)
    observed = read_value(combo)
    if normalize_text(observed) != normalize_text(option):
        raise ManualReviewRequired(
            spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: wanted {option!r}, shows {observed!r}"
        )


def set_checkbox(checkbox: Any, checked: bool, *, spec_step: str, field_name: str) -> None:
    def state() -> bool:
        return bool(checkbox.iface_toggle.CurrentToggleState)

    if state() != checked:
        checkbox.iface_toggle.Toggle()
    if state() != checked:
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name} did not toggle")
