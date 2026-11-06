"""Typing and reading values through UIA, with read-back verification ("verify each step")."""

from __future__ import annotations

import contextlib
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


def type_into(element: Any, text: str, commit_key: str = "") -> None:
    """Focus, select all, type. Typing (not ValuePattern.SetValue) fires SWT's own modify/verify
    listeners, so Fakturama recalculates exactly as for a human user. No commit key by default:
    several Fakturama fields are multi-line, where Tab inserts a tab character (seen in discovery)."""
    element.set_focus()
    if not _has_focus(element):  # UIA focus did not take (seen live): click inside the field
        element.click_input()
    keyboard.send_keys("^a{DELETE}", pause=0.02)
    if text:
        keyboard.send_keys(escape_send_keys(text), with_spaces=True, pause=0.01)
    if commit_key:
        keyboard.send_keys(commit_key, pause=0.02)


def _has_focus(element: Any) -> bool:
    try:
        return bool(element.has_keyboard_focus())
    except Exception:
        return False


def exact_text(value: str) -> str:
    """Read-back comparison: trims the ends only, so a stray tab or newline inside is a mismatch."""
    return value.strip()


def set_and_verify(
    element: Any,
    value: str,
    *,
    spec_step: str,
    field_name: str,
    normalize: Callable[[str], str] = exact_text,
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


def combo_options(combo: Any) -> list[str]:
    """Visible option texts of a ComboBox (its list items exist while it is expanded)."""
    combo.expand()
    try:
        return [str(item.element_info.name) for item in combo.descendants(control_type="ListItem")]
    finally:
        combo.collapse()


def select_tab_item(item: Any) -> None:
    """SWT tab folders: SelectionItem.Select() either raises ('Member not found') or returns without
    switching the editor, so verify IsSelected and fall back to clicking the tab's UIA rectangle."""

    def is_selected() -> bool:
        try:
            return bool(item.iface_selection_item.CurrentIsSelected)
        except Exception:
            return False

    if is_selected():
        return
    with contextlib.suppress(Exception):
        item.iface_selection_item.Select()
    if not is_selected():
        item.click_input()


def select_combo_option(combo: Any, option: str, *, spec_step: str, field_name: str) -> None:
    """Select the ComboBox entry whose text equals `option` after normalization (Fakturama pads some
    options with spaces, e.g. 'Credit transfer '), then verify the selection."""
    if normalize_text(read_value(combo)) == normalize_text(option):
        return
    exact = [o for o in combo_options(combo) if normalize_text(o) == normalize_text(option)]
    if len(exact) != 1:
        raise ManualReviewRequired(
            spec_step, ReviewReason.UI_ELEMENT_NOT_FOUND, f"{field_name}: {len(exact)} options named {option!r}"
        )
    combo.select(exact[0])
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
