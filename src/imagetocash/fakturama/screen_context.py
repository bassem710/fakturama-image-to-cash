"""Shared plumbing for every Fakturama screen object: locating, clicking, tabs, views, Save, OCR tables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pywinauto import mouse

from imagetocash.automation.input import select_tab_item
from imagetocash.automation.locators import Locator, build_locator, largest_leaf_pane, locate
from imagetocash.automation.ocr_table import OcrTable, OcrTableReader, OcrTableRow
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

    # --- locating and acting ---------------------------------------------------------------
    def main(self) -> Any:
        return self.session.main_wrapper()

    def find(self, screen: str, key: str, scope: Any | None = None, timeout: float | None = None) -> Any:
        return locate(
            scope if scope is not None else self.main(),
            self.selectors.locator(screen, key),
            timeout if timeout is not None else self.settings.timeouts.element,
        )

    @staticmethod
    def press(element: Any) -> None:
        """Invoke pattern when the control has one; otherwise click the centre of its UIA rectangle."""
        try:
            element.iface_invoke.Invoke()
        except Exception:
            element.click_input()

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
        self.find("main", panel_key).click_input()  # navigation entry: no Invoke pattern
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
        select_tab_item(self.editor_item(tab))

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
        """'Data > VATs' etc.: the entries of the navigation view's Data group (verified names)."""
        title = str(self.selectors.value("data_views", view_key))
        self.session.bring_to_front()
        entry = locate(self.main(), build_locator({"control_type": "Text", "name": title}))
        entry.click_input()
        self.content_pane(title)
        return title

    # --- OCR tables -------------------------------------------------------------------------------
    def read_table_rows(self, table: Any, columns: Mapping[str, str]) -> list[tuple[dict[str, str], OcrTableRow]]:
        """OCR the custom-drawn table inside its UIA rectangle; map header titles to record fields."""

        last: list[OcrTable] = []

        def read() -> tuple[tuple[tuple[str, str], ...], ...]:
            last[:] = [self.tables.read(ScreenRect.of(table), expected_headers=tuple(columns))]
            return tuple(tuple(sorted(r.cells.items())) for r in last[0].rows)

        wait_until_stable(read, timeout=self.settings.timeouts.list_stable, what="the list")
        ocr_table = last[0]
        mapped = []
        for row in ocr_table.rows:
            record = {
                field: next((v for k, v in row.cells.items() if normalize_text(k) == normalize_text(title)), "")
                for title, field in columns.items()
            }
            if any(record.values()):
                mapped.append((record, row))
        return mapped

    @staticmethod
    def table_in(scope: Any) -> Any:
        table = largest_leaf_pane(scope)
        if table is None:
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "no table pane found")
        return table

    @staticmethod
    def click_point(point: tuple[int, int], double: bool = False) -> None:
        """Click a point that OCR measured at runtime inside a UIA rectangle."""
        (mouse.double_click if double else mouse.click)(coords=point)

    # --- formatting ---------------------------------------------------------------------------------
    @property
    def ui_date_parse_format(self) -> str:
        return self.settings.ui_date_format.replace("{day}", "%d")

    def format_ui_date(self, value: date) -> str:
        return value.strftime(self.settings.ui_date_format.replace("{day}", str(value.day)))
