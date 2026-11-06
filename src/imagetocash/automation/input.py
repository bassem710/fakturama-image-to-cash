"""Typing and reading values through UIA, with read-back verification ("verify each step")."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

from pywinauto import keyboard

from imagetocash.automation.focus import focus, has_keyboard_focus
from imagetocash.automation.locators import find_first
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

_SEND_KEYS_SPECIALS = set("+^%~(){}[]")
READ_BACK_SECONDS = 1.0  # how long a typed value may take to appear in the field


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
    if not has_keyboard_focus(element):  # UIA focus did not take (seen live): click inside the field
        element.click_input()
    keyboard.send_keys("^a{DELETE}", pause=0.02)
    if text:
        keyboard.send_keys(escape_send_keys(text), with_spaces=True, pause=0.005)
    if commit_key:
        keyboard.send_keys(commit_key, pause=0.02)


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
    """Type `value`, read it back, retry once, then stop for manual review.

    Typing on purpose, not ValuePattern.SetValue: found live that SetValue changes the text on screen
    (and passes a read-back) while Fakturama's data binding never receives it, so a Debtor was saved
    without its Company. Keystrokes go through SWT's own listeners, exactly like a person typing."""
    observed = ""
    for _ in range(attempts):
        type_into(element, value)
        # Found live: a busy field (E-Mail validates per key) can lag the last keystrokes, so the
        # read-back polls briefly before calling it a mismatch.
        def settled() -> str | None:
            text = reader(element)
            return text if normalize(text) == normalize(value) else None

        try:
            return wait_until(settled, timeout=READ_BACK_SECONDS, what=field_name, done=lambda _: True, interval=0.05)
        except WaitTimeout:
            observed = reader(element)
    raise ManualReviewRequired(
        spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: typed {value!r}, field shows {observed!r}"
    )


def combo_options(combo: Any) -> list[str]:
    """Visible option texts of a ComboBox (its list items exist while it is expanded)."""
    combo.expand()
    try:  # the list items appear in the UIA tree a moment after Expand
        return wait_until(
            lambda: [str(item.element_info.name) for item in combo.descendants(control_type="ListItem")],
            timeout=2.0,
            what="dropdown options",
            interval=0.05,
        )
    except WaitTimeout:
        return []
    finally:
        combo.collapse()


def is_selected(item: Any) -> bool:
    """SelectionItem.IsSelected (a tab, a list item); False when the element has no such pattern."""
    try:
        return bool(item.iface_selection_item.CurrentIsSelected)
    except Exception:
        return False


def select_tab_item(item: Any) -> None:
    """SWT tab folders: SelectionItem.Select() either raises ('Member not found') or returns without
    switching the editor, so verify IsSelected and fall back to clicking the tab's UIA rectangle."""
    if is_selected(item):
        return
    with contextlib.suppress(Exception):
        item.iface_selection_item.Select()
    if not is_selected(item):
        item.click_input()


def select_combo_option(
    combo: Any, option: str, *, spec_step: str, field_name: str, options: Sequence[str] | None = None
) -> None:
    """Select the ComboBox entry whose text equals `option` after normalization (Fakturama pads some
    options with spaces, e.g. 'Credit transfer '), then verify the selection.

    Found live (run #15): SelectionItem.Select() on an option changes the combo's TEXT but fires no
    SWT Selection event, so Fakturama's data binding keeps the old value: a Product was saved with
    VAT 'Tax-free' while its editor showed 'VAT 19%'. So the choice is made the way a user makes it:
    keyboard Up/Down from the current option (fires Selection), else a click on the option element
    inside the expanded dropdown (element-relative, never a fixed point). `options` reuses a list the
    caller has just read from this combo (saves a second expand).

    First choice is a search: type the option's letters until the combo shows it (a few keys instead of
    up to ~80 Down presses for 'Germany' in Country), then one arrow away and back. Found live: a
    selection made by letters alone left the binding on an earlier prefix hit (Germany shown, Georgia
    saved); an arrow-key selection always reaches it. Up/Down from the current option is the fallback."""
    if normalize_text(read_value(combo)) == normalize_text(option):
        return
    options = list(options) if options is not None else combo_options(combo)
    exact = [i for i, o in enumerate(options) if normalize_text(o) == normalize_text(option)]
    if len(exact) != 1:
        raise ManualReviewRequired(
            spec_step, ReviewReason.UI_ELEMENT_NOT_FOUND, f"{field_name}: {len(exact)} options named {option!r}"
        )
    target = exact[0]
    if not _search(combo, options, target):
        shown = normalize_text(read_value(combo))
        current = next((i for i, o in enumerate(options) if normalize_text(o) == shown), None)
        if current is not None and current != target:
            combo.set_focus()
            keyboard.send_keys(("{DOWN}" if target > current else "{UP}") * abs(target - current), pause=0.03)
    if normalize_text(read_value(combo)) != normalize_text(option):
        _click_list_item(combo, options[target])
    observed = read_value(combo)
    if normalize_text(observed) != normalize_text(option):
        raise ManualReviewRequired(
            spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name}: wanted {option!r}, shows {observed!r}"
        )


def type_until_shown(send: Callable[[str], None], shown: Callable[[], str], text: str) -> bool:
    """Windows combo search: each typed character extends a prefix search over the options. Type
    `text` one character at a time; True as soon as the combo shows `text`, False if it never does."""
    wanted = normalize_text(text)
    for character in text:
        send(escape_send_keys(character))
        if normalize_text(shown()) == wanted:
            return True
    return False


def arrow_nudge(target: int, count: int) -> str:
    """One arrow away from the target and back, so the LAST selection change is an arrow key (which
    Fakturama's binding always receives). On the last option the way away is Up."""
    if count < 2:
        return ""
    return "{UP}{DOWN}" if target == count - 1 else "{DOWN}{UP}"


def _search(combo: Any, options: Sequence[str], target: int) -> bool:
    """Search the closed, focused combo by letters, then nudge. Skipped for an editable combo (an
    `Edit` child), where typing only changes the text and selects nothing. False -> caller falls back."""
    if find_first(combo, control_type="Edit") is not None or not focus(combo):
        return False

    def send(keys: str) -> None:
        keyboard.send_keys(keys, with_spaces=True, pause=0.03)

    if not type_until_shown(send, lambda: read_value(combo), options[target]):
        return False
    if nudge := arrow_nudge(target, len(options)):
        keyboard.send_keys(nudge, pause=0.03)
    return normalize_text(read_value(combo)) == normalize_text(options[target])


def _click_list_item(combo: Any, name: str) -> None:
    """Expand, then click the option's own UIA element (the dropdown closes on the click)."""
    combo.expand()
    item = next((i for i in combo.descendants(control_type="ListItem") if i.element_info.name == name), None)
    if item is None:
        with contextlib.suppress(Exception):
            combo.collapse()
        return
    item.click_input()


def set_checkbox(checkbox: Any, checked: bool, *, spec_step: str, field_name: str) -> None:
    """Toggle pattern, then element click; each followed by a short poll. Found live (run #24, the
    Invoice 'paid' box): the toggle state reads stale for a moment after a successful Toggle()."""

    def state() -> bool:
        return bool(checkbox.iface_toggle.CurrentToggleState)

    def settled() -> bool:
        try:
            return wait_until(lambda: state() == checked, timeout=1.0, what=field_name, interval=0.05)
        except WaitTimeout:
            return False

    if state() == checked:
        return
    checkbox.iface_toggle.Toggle()
    if settled():
        return
    checkbox.click_input()  # element-relative fallback
    if not settled():
        raise ManualReviewRequired(spec_step, ReviewReason.VALUE_MISMATCH, f"{field_name} did not toggle")
