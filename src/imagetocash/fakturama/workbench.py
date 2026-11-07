"""Fakturama's Eclipse workbench: editor tabs (tracked by identity), views (Data lists) and Save.

Editors are tracked by identity, not by title. A leftover draft can carry the same title ("New
Order") as the editor this run opens. UIA runtime ids are shared by all tabs of one tab folder, and
Fakturama appends new editors at the end of their folder, so an editor is identified by (folder,
position) at the moment it opens. Older drafts at earlier positions are never activated, filled or
saved.

Speed: a whole-window UIA scan costs ~0.4 s on Fakturama, so an editor's tab item and content pane
are kept once found and re-checked with cheap live reads (is the tab still selected?) instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from imagetocash.automation.input import is_selected, select_tab_item
from imagetocash.automation.locators import find_first
from imagetocash.automation.run_log import get_logger
from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

if TYPE_CHECKING:
    from imagetocash.fakturama.screen_context import ScreenContext

NEW_PANEL_GRACE_SECONDS = 4.0  # the New panel entry sometimes only re-focuses an open "new" editor


@dataclass(frozen=True)
class EditorTab:
    folder_id: tuple[int, ...]
    index: int


TabSnapshot = Mapping[tuple[int, ...], int]  # tab folder -> number of tabs


class Workbench:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._items: dict[EditorTab, Any] = {}
        self._panes: dict[EditorTab, Any] = {}

    # --- editor tabs ---------------------------------------------------------------------------
    def snapshot(self) -> dict[tuple[int, ...], int]:
        """How many tabs each tab folder has now; pass it to wait_for_new() after opening an editor."""
        return {folder: len(items) for folder, items in self._folders().items()}

    def wait_for_new(self, before: TabSnapshot, title_prefix: str = "", timeout: float | None = None) -> EditorTab:
        """The editor tab opened since `before` (a brand-new folder is an editor's inner tabs, never an
        editor itself)."""
        return wait_until(
            lambda: self._new_tab(before, title_prefix),
            timeout=timeout if timeout is not None else self._ctx.settings.timeouts.dialog,
            what="the new editor tab",
        )

    def wait_for_record_editor(self, before: TabSnapshot, title: str) -> EditorTab:
        """The editor a list double-click showed for the record `title`: a NEW tab, or (found live:
        Fakturama never opens a record twice) the record's already open tab, now selected. A tab
        whose title merely shares the name but is not selected is never taken."""

        def probe() -> EditorTab | None:
            folders = self._folders()  # one window scan per poll (~0.4 s each)
            if tab := self._new_tab(before, title, folders):
                return tab
            for folder, items in folders.items():
                for index, item in enumerate(items):
                    if str(item.element_info.name).lstrip("*") == title and is_selected(item):
                        tab = EditorTab(folder, index)
                        self._items[tab] = item
                        return tab
            return None

        return wait_until(probe, timeout=self._ctx.settings.timeouts.element, what=f"the editor of '{title}'")

    def open_new(self, panel_key: str, toolbar_key: str) -> EditorTab:
        """Spec: click the entry in the left New panel. If that only re-focuses an existing editor (no
        fresh 'New ...' tab soon), use the equivalent toolbar button."""
        ctx = self._ctx
        prefix = str(ctx.selectors.value("main", "new_editor_title_prefix"))
        ctx.session.bring_to_front()
        before = self.snapshot()
        ctx.find("main", panel_key).click_input()  # New panel entry: no pattern (element click fallback)
        ctx.invalidate()
        try:
            return self.wait_for_new(before, prefix, timeout=NEW_PANEL_GRACE_SECONDS)
        except WaitTimeout:
            get_logger().warning(f"New panel '{panel_key}' opened no editor; using the toolbar button")
            ctx.press(ctx.find("main", toolbar_key))
            return self.wait_for_new(before, prefix)

    def title(self, tab: EditorTab) -> str:
        return str(self._item(tab).element_info.name).lstrip("*")

    def is_dirty(self, tab: EditorTab) -> bool:
        return str(self._item(tab).element_info.name).startswith("*")

    def activate(self, tab: EditorTab) -> None:
        self._ctx.session.bring_to_front()
        item = self._item(tab)
        if not is_selected(item):
            select_tab_item(item)
            self._ctx.invalidate()
            self._panes.clear()  # only the ACTIVE editor's controls exist in the UIA tree

    def pane(self, tab: EditorTab) -> Any:
        """The active editor's content pane. Only the active editor's controls exist in the UIA tree,
        so after activating our tab the pane named after it is ours even when another (hidden) editor
        has the same title."""
        self.activate(tab)
        if tab not in self._panes:
            self._panes[tab] = self.content_pane(self.title(tab))
        return self._panes[tab]

    def save(self, tab: EditorTab) -> None:
        """Toolbar Save, exactly once, then wait until THIS editor loses its dirty marker '*'."""
        ctx = self._ctx
        self.activate(tab)
        ctx.press(ctx.find("main", "save"))
        wait_until(
            lambda: not self.is_dirty(tab),
            timeout=ctx.settings.timeouts.dialog,
            what=f"'{self.title(tab)}' to be saved",
        )
        self._panes.pop(tab, None)  # the editor is renamed (New Order -> PO...): find its pane again

    # --- views ---------------------------------------------------------------------------------
    def content_pane(self, title: str) -> Any:
        """The Pane named after an editor/view tab holds that part's controls (verified: 'New Order')."""
        return wait_until(
            lambda: find_first(self._ctx.main(), control_type="Pane", name=title),
            timeout=self._ctx.settings.timeouts.element,
            what=f"content of '{title}'",
        )

    def activate_view(self, title: str) -> None:
        """Views (Documents, VATs, ...) by title; editors use activate() instead."""
        self._ctx.session.bring_to_front()
        tab = wait_until(
            lambda: find_first(self._ctx.main(), control_type="TabItem", name=title),
            timeout=self._ctx.settings.timeouts.element,
            what=f"tab '{title}'",
        )
        if not is_selected(tab):
            select_tab_item(tab)
            self._ctx.invalidate()

    def open_data_view(self, view_key: str) -> str:
        """Spec 'Data > VATs' etc.: the Data menu (ExpandCollapse) and its item (Invoke)."""
        ctx = self._ctx
        title = str(ctx.selectors.value("data_views", view_key))
        ctx.session.bring_to_front()
        ctx.find("main", "data_menu").iface_expand_collapse.Expand()
        item = wait_until(
            lambda: find_first(ctx.main(), control_type="MenuItem", name=title),
            timeout=ctx.settings.timeouts.element,
            what=f"Data > {title}",
        )
        item.iface_invoke.Invoke()
        ctx.invalidate()
        self.content_pane(title)
        return title

    def view_folder(self, title: str) -> Any:
        """The tab folder whose selected tab is the view `title` (its toolbar holds the green +)."""
        return wait_until(
            lambda: find_first(self._ctx.main(), control_type="Tab", name=title),
            timeout=self._ctx.settings.timeouts.element,
            what=f"view '{title}'",
        )

    # --- internals ------------------------------------------------------------------------------
    def _folders(self) -> dict[tuple[int, ...], list[Any]]:
        folders: dict[tuple[int, ...], list[Any]] = {}
        for item in self._ctx.main().descendants(control_type="TabItem"):
            folders.setdefault(tuple(item.element_info.runtime_id), []).append(item)
        return folders

    def _new_tab(
        self, before: TabSnapshot, title_prefix: str, folders: dict[tuple[int, ...], list[Any]] | None = None
    ) -> EditorTab | None:
        for folder, items in (folders if folders is not None else self._folders()).items():
            if folder not in before:
                continue
            for index in range(before[folder], len(items)):
                if str(items[index].element_info.name).lstrip("*").startswith(title_prefix):
                    tab = EditorTab(folder, index)
                    self._items[tab] = items[index]
                    return tab
        return None

    def _item(self, tab: EditorTab) -> Any:
        item = self._items.get(tab)
        if item is not None and _still_in_folder(item, tab):
            return item
        items = self._folders().get(tab.folder_id, [])
        if tab.index >= len(items):
            raise ManualReviewRequired("-", ReviewReason.UI_ELEMENT_NOT_FOUND, "the editor tab this run opened is gone")
        self._items[tab] = items[tab.index]
        return items[tab.index]


def _still_in_folder(item: Any, tab: EditorTab) -> bool:
    try:
        return tuple(item.element_info.runtime_id) == tab.folder_id
    except Exception:  # the element is gone
        return False
