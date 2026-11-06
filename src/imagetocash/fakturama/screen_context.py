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
from imagetocash.automation.waiting import wait_until, wait_until_stable
from imagetocash.cli.config import Settings
from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason


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

    def save_via_toolbar(self, editor_title: str) -> None:
        """Toolbar Save, exactly once, then wait until the editor tab loses its dirty marker '*'."""
        self.press(self.find("main", "save"))
        wait_until(
            lambda: not any(t.startswith("*") and editor_title in t for t in self.tab_titles()),
            timeout=self.settings.timeouts.dialog,
            what=f"'{editor_title}' to be saved",
        )

    # --- tabs and views ------------------------------------------------------------------------
    def tab_items(self) -> list[Any]:
        return list(self.main().descendants(control_type="TabItem"))

    def tab_titles(self) -> list[str]:
        return [str(t.element_info.name) for t in self.tab_items()]

    def activate_tab(self, title: str) -> None:
        self.session.bring_to_front()
        tab = wait_until(
            lambda: next((t for t in self.tab_items() if t.element_info.name.lstrip("*") == title), None),
            timeout=self.settings.timeouts.element,
            what=f"tab '{title}'",
        )
        select_tab_item(tab)

    def wait_for_new_tab(self, before: list[str], title_prefix: str = "") -> str:
        def new_title() -> str | None:
            fresh = [t for t in self.tab_titles() if t not in before and t.lstrip("*").startswith(title_prefix)]
            return fresh[0].lstrip("*") if fresh else None

        return wait_until(new_title, timeout=self.settings.timeouts.dialog, what="a new editor tab")

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
