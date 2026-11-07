"""What every Fakturama screen object shares: the session, the selector map, settings, and fast element
lookup. Editor/view handling lives in workbench.py, list reading in tables.py."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from imagetocash.automation.locators import CachedScope, Locator, build_locator, locate
from imagetocash.automation.ocr_table import OcrTableReader
from imagetocash.automation.session import DesktopSession
from imagetocash.config import Settings
from imagetocash.fakturama.tables import ListReader
from imagetocash.fakturama.workbench import EditorTab, Workbench


class SelectorMap:
    """config/selectors.yaml: every UI element and UI word the automation uses, by screen and key."""

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self._raw = raw

    @classmethod
    def load(cls, path: Path) -> SelectorMap:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def locator(self, screen: str, key: str) -> Locator:
        return build_locator(self._raw[screen][key])

    def value(self, screen: str, key: str) -> Any:
        return self._raw[screen][key]


def connect_session(settings: Settings, selectors: SelectorMap) -> DesktopSession:
    """Attach to (or start) Fakturama and address its main window by handle."""
    return DesktopSession.attach_or_launch(
        settings.fakturama_exe,
        main_window_class=str(selectors.value("app", "main_window_class")),
        main_title_prefix=str(selectors.value("app", "main_title_prefix")),
        error_dialog_title=str(selectors.value("app", "internal_error_title")),
        timeout=settings.timeouts.app_start,
    )


@dataclass
class ScreenContext:
    session: DesktopSession
    selectors: SelectorMap
    ocr: OcrTableReader
    settings: Settings
    last_record_editor: EditorTab | None = None  # opened by a list's green + (VAT, payment method)
    saved_vat_codes: dict[str, str] = field(default_factory=dict)  # VAT name -> code this run set (3.6)
    workbench: Workbench = field(init=False)
    lists: ListReader = field(init=False)
    _generation: int = 0
    _scopes: dict[tuple[int, ...], tuple[int, CachedScope]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workbench = Workbench(self)
        self.lists = ListReader(self)

    def main(self) -> Any:
        return self.session.main_wrapper()

    def find(self, screen: str, key: str, scope: Any | None = None, timeout: float | None = None) -> Any:
        """The element `screen.key` from selectors.yaml inside `scope` (default: the main window).

        Inside an editor or dialog, one snapshot of that scope serves all its fields until the UI
        changes (`invalidate`). The main window is too big to snapshot (~0.5 s): it is searched live,
        where a named lookup stops at the first match. A miss falls back to live polling."""
        locator = self.selectors.locator(screen, key)
        wait = timeout if timeout is not None else self.settings.timeouts.element
        if scope is None:
            return locate(self.main(), locator, wait)
        try:
            found = locator.find(self._cached(scope))
            if found is not None:
                return found
        except Exception:  # a stale snapshot after a UI change
            pass
        self.invalidate()
        return locate(scope, locator, wait)

    def _cached(self, scope: Any) -> CachedScope:
        key = tuple(scope.element_info.runtime_id or ()) or (id(scope),)
        entry = self._scopes.get(key)
        if entry is None or entry[0] != self._generation:
            entry = (self._generation, CachedScope(scope))
            self._scopes[key] = entry
        return entry[1]

    def invalidate(self) -> None:
        """The UI changed (a click, tab switch, dialog, save): snapshots are rebuilt on the next find."""
        self._generation += 1

    def press(self, element: Any) -> None:
        """Invoke pattern; only when a control has none, a click on the element itself."""
        try:
            element.iface_invoke.Invoke()
        except Exception:
            element.click_input()
        self.invalidate()

    @property
    def ui_date_parse_format(self) -> str:
        return self.settings.ui_date_format.replace("{day}", "%d")
