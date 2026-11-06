"""Keyboard focus through UIA: confirm where keys will go before sending them (never type blind)."""

from __future__ import annotations

from typing import Any

from pywinauto.uia_defines import IUIA

from imagetocash.automation.waiting import WaitTimeout, settle, wait_until

FOCUS_SETTLE_SECONDS = 0.15  # keys sent right after a focus change can be dropped (measured)


def has_keyboard_focus(element: Any) -> bool:
    """True when UIA reports `element` itself as the focused element."""
    try:
        iuia = IUIA().iuia
        return bool(iuia.CompareElements(iuia.GetFocusedElement(), element.element_info.element))
    except Exception:
        return False


def focus(element: Any, *, timeout: float = 2.0, settle_seconds: float = FOCUS_SETTLE_SECONDS) -> bool:
    """Give `element` the keyboard focus, wait until UIA confirms it, then let it settle.
    Returns False when the focus was never confirmed (the caller decides on a fallback)."""
    element.set_focus()
    try:
        wait_until(lambda: has_keyboard_focus(element), timeout=timeout, what="keyboard focus")
    except WaitTimeout:
        return False
    settle(settle_seconds)
    return True
