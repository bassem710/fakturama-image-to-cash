"""Shared plumbing for every Fakturama screen object: locating, clicking, tabs, views, Save, OCR tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from imagetocash.automation.clipboard_table import copy_table
from imagetocash.automation.input import select_tab_item
from imagetocash.automation.locators import CachedScope, Locator, build_locator, largest_leaf_pane, locate
from imagetocash.automation.ocr_table import OcrTable, OcrTableReader
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.screen_ocr import ScreenRect
from imagetocash.automation.session import DesktopSession
from imagetocash.automation.waiting import WaitTimeout, wait_until, wait_until_stable
from imagetocash.cli.config import Settings
from imagetocash.domain.matching import normalize_ocr_text, normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason


@dataclass(frozen=True)
class EditorTab:
    folder_id: tuple[int, ...]
    index: int


class SelectorMap:
    def __init__(self, raw: Mapping[str, Any]) -> None:
        self._raw = raw

    @classmethod
    def load(cls, path: Path) -> SelectorMap:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def locator(self, screen: str, key: str) -> Locator:
        return build_locator(self._raw[screen][key])

    def value(self, screen: str, key: str) -> Any:
        return self._raw[screen][key]


@dataclass
class ScreenContext:
    session: DesktopSession
    selectors: SelectorMap
    tables: OcrTableReader
    settings: Settings
    last_record_editor: EditorTab | None = None  # set by a list's green + (VAT, payment method)
    _generation: int = 0
    _scopes: dict[tuple[int, ...], tuple[int, CachedScope]] | None = None

    # --- locating and acting ---------------------------------------------------------------
    def main(self) -> Any:
        return self.session.main_wrapper()

    def find(self, screen: str, key: str, scope: Any | None = None, timeout: float | None = None) -> Any:
        """One cached tree walk per scope (ScreenIndex): many fields of one editor resolve from the
        same snapshot. A miss, or a stale snapshot after a UI change, falls back to live polling."""
        live_scope = scope if scope is not None else self.main()
        locator = self.selectors.locator(screen, key)
        try:
            found = locator.find(self._cached(live_scope))
            if found is not None:
                return found
        except Exception:
            pass
        self.invalidate()
        return locate(live_scope, locator, timeout if timeout is not None else self.settings.timeouts.element)

    def _cached(self, scope: Any) -> CachedScope:
        if self._scopes is None:
            self._scopes = {}
        key = tuple(scope.element_info.runtime_id or ()) or (id(scope),)
        entry = self._scopes.get(key)
        if entry is None or entry[0] != self._generation:
            entry = (self._generation, CachedScope(scope))
            self._scopes[key] = entry
        return entry[1]

    def invalidate(self) -> None:
        """The UI changed structurally (tab switch, dialog, save): rebuild snapshots on next find."""
        self._generation += 1

    def press(self, element: Any) -> None:
        """Invoke pattern; only when a control has none, a click on the element itself."""
        try:
            element.iface_invoke.Invoke()
        except Exception:
            element.click_input()
        self.invalidate()

    # --- tabs and views ------------------------------------------------------------------------
    def tab_items(self) -> list[Any]:
        return list(self.main().descendants(control_type="TabItem"))

    def tab_titles(self) -> list[str]:
        return [str(t.element_info.name) for t in self.tab_items()]

    def activate_tab(self, title: str) -> None:
        """Views (Documents, VATs, ...) by title; editors use activate_editor() instead."""
        self.session.bring_to_front()
        tab = wait_until(
            lambda: next((t for t in self.tab_items() if t.element_info.name.lstrip("*") == title), None),
            timeout=self.settings.timeouts.element,
            what=f"tab '{title}'",
        )
        select_tab_item(tab)
        self.invalidate()

    # --- editors, tracked by identity, not by title -----------------------------------------------
    # A leftover draft can carry the same title ("New Order") as the editor this run opens. UIA
    # runtime ids are shared by all tabs of one tab folder, and Fakturama appends new editors at
    # the end of their folder, so an editor is identified by (folder, position) at the moment it
    # opens. Older drafts at earlier positions are never activated, filled or saved.
    def _tab_folders(self) -> dict[tuple[int, ...], list[Any]]:
        folders: dict[tuple[int, ...], list[Any]] = {}
        for item in self.tab_items():
            folders.setdefault(tuple(item.element_info.runtime_id), []).append(item)
        return folders

    def tab_snapshot(self) -> dict[tuple[int, ...], int]:
        return {folder: len(items) for folder, items in self._tab_folders().items()}

    def wait_for_new_tab(self, before: Mapping[tuple[int, ...], int], title_prefix: str = "") -> EditorTab:
        # A brand-new folder is an editor's inner tabs (Addresses, ...), never an editor itself.
        return wait_until(
            lambda: self._new_tab(before, title_prefix),
            timeout=self.settings.timeouts.dialog,
            what="the new editor tab",
        )

    def open_new_editor(self, panel_key: str, toolbar_key: str) -> EditorTab:
        """Spec: click the entry in the left New panel. If that only re-focuses an existing editor (no
        fresh 'New ...' tab within a few seconds), use the equivalent toolbar button."""
        prefix = str(self.selectors.value("main", "new_editor_title_prefix"))
        self.session.bring_to_front()
        before = self.tab_snapshot()
        self.find("main", panel_key).click_input()  # New panel entry: no pattern (element click fallback)
        self.invalidate()
        try:
            return wait_until(lambda: self._new_tab(before, prefix), timeout=4, what="a new editor from the New panel")
        except WaitTimeout:
            self.press(self.find("main", toolbar_key))
            return self.wait_for_new_tab(before, title_prefix=prefix)

    def _new_tab(self, before: Mapping[tuple[int, ...], int], title_prefix: str) -> EditorTab | None:
        for folder, items in self._tab_folders().items():
            if folder not in before:
                continue
            for index in range(before[folder], len(items)):
                if str(items[index].element_info.name).lstrip("*").startswith(title_prefix):
                    return EditorTab(folder, index)
        return None

    def editor_titled(self, title: str) -> EditorTab:
        """An already open editor (e.g. re-focused by a double-click on its list row), by title."""
        for folder, items in self._tab_folders().items():
            for index, item in enumerate(items):
                if normalize_ocr_text(str(item.element_info.name).lstrip("*")) == normalize_ocr_text(title):
                    return EditorTab(folder, index)
        raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, f"no editor titled {title!r}")

    def editor_item(self, tab: EditorTab) -> Any:
        items = self._tab_folders().get(tab.folder_id, [])
        if tab.index >= len(items):
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "the editor tab this run opened is gone")
        return items[tab.index]

    def editor_title(self, tab: EditorTab) -> str:
        return str(self.editor_item(tab).element_info.name).lstrip("*")

    def is_dirty(self, tab: EditorTab) -> bool:
        return str(self.editor_item(tab).element_info.name).startswith("*")

    def activate_editor(self, tab: EditorTab) -> None:
        self.session.bring_to_front()
        item = self.editor_item(tab)
        try:
            already = bool(item.iface_selection_item.CurrentIsSelected)
        except Exception:
            already = False
        if not already:
            select_tab_item(item)
            self.invalidate()

    def editor_pane(self, tab: EditorTab) -> Any:
        """Only the ACTIVE editor's controls exist in the UIA tree, so after activating our tab the
        pane named after it is ours even when another (hidden) editor has the same title."""
        self.activate_editor(tab)
        return self.content_pane(self.editor_title(tab))

    def save_editor(self, tab: EditorTab) -> None:
        """Toolbar Save, exactly once, then wait until THIS editor loses its dirty marker '*'."""
        self.activate_editor(tab)
        self.press(self.find("main", "save"))
        wait_until(
            lambda: not self.is_dirty(tab),
            timeout=self.settings.timeouts.dialog,
            what=f"'{self.editor_title(tab)}' to be saved",
        )

    def content_pane(self, title: str) -> Any:
        """The Pane named after an editor/view tab holds that editor's controls (verified: 'New Order')."""
        return wait_until(
            lambda: next(
                (p for p in self.main().descendants(control_type="Pane") if p.element_info.name == title), None
            ),
            timeout=self.settings.timeouts.element,
            what=f"content of '{title}'",
        )

    def open_data_view(self, view_key: str) -> str:
        """Spec 'Data > VATs' etc.: the Data menu (ExpandCollapse) and its item (Invoke)."""
        title = str(self.selectors.value("data_views", view_key))
        self.session.bring_to_front()
        menu = self.find("main", "data_menu")
        menu.iface_expand_collapse.Expand()
        item = wait_until(
            lambda: next(
                (m for m in self.main().descendants(control_type="MenuItem") if m.element_info.name == title), None
            ),
            timeout=self.settings.timeouts.element,
            what=f"Data > {title}",
        )
        item.iface_invoke.Invoke()
        self.invalidate()
        self.content_pane(title)
        return title

    # --- custom-drawn tables ---------------------------------------------------------------------
    def read_table_rows(
        self,
        table: Any,
        columns: Mapping[str, str],
        order: Sequence[str] = (),
        percent_fields: Sequence[str] = (),
    ) -> list[dict[str, str]]:
        """Rows of a NatTable as records. First the clipboard (Ctrl+A / Ctrl+C: exact model values in
        display order, no coordinates, no OCR); `order` names the field of each display column ('' to
        skip one). If the copy is empty or has a different shape, read it with OCR inside the table's
        UIA rectangle instead (read-only)."""
        if order:
            # Found live: Ctrl+C on an EMPTY NatTable makes Fakturama show an 'Internal Error' dialog
            # (NullPointerException). So a quick read-only look first: no data rows -> no copy.
            if not self.tables.has_data_rows(ScreenRect.of(table), expected_headers=tuple(columns)):
                return []
            copied = copy_table(table)
            if copied is not None and all(len(row) == len(order) for row in copied):
                records = []
                for row in copied:
                    record = {field: cell for field, cell in zip(order, row, strict=True) if field}
                    for field in percent_fields:  # raw fraction 0.19 -> '19%'
                        if record.get(field):
                            record[field] = _fraction_to_percent(record[field])
                    if any(record.values()):
                        records.append(record)
                return records
            if copied:
                get_logger().warning(f"table copy had an unexpected shape ({len(copied[0])} cells), using OCR")
        return self._read_table_ocr(table, columns)

    def _read_table_ocr(self, table: Any, columns: Mapping[str, str]) -> list[dict[str, str]]:
        last: list[OcrTable] = []

        def read() -> tuple[tuple[tuple[str, str], ...], ...]:
            last[:] = [self.tables.read(ScreenRect.of(table), expected_headers=tuple(columns))]
            return tuple(tuple(sorted(r.cells.items())) for r in last[0].rows)

        wait_until_stable(read, timeout=self.settings.timeouts.list_stable, what="the list")
        records = []
        for row in last[0].rows:
            record = {
                field: next((v for k, v in row.cells.items() if normalize_text(k) == normalize_text(title)), "")
                for title, field in columns.items()
            }
            if any(record.values()):
                records.append(record)
        return records

    @staticmethod
    def table_in(scope: Any) -> Any:
        table = largest_leaf_pane(scope)
        if table is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "no table pane found")
        return table

    # --- formatting ---------------------------------------------------------------------------------
    @property
    def ui_date_parse_format(self) -> str:
        return self.settings.ui_date_format.replace("{day}", "%d")

    def format_ui_date(self, value: date) -> str:
        return value.strftime(self.settings.ui_date_format.replace("{day}", str(value.day)))


def _fraction_to_percent(raw: str) -> str:
    try:
        return f"{(Decimal(raw) * 100).normalize():f}%"
    except InvalidOperation:
        return raw
