"""What every editor screen shares: its tab (tracked by identity), its pane and its fields."""

from __future__ import annotations

from typing import Any, ClassVar

from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.workbench import EditorTab


class EditorScreen:
    section: ClassVar[str]  # the config/selectors.yaml section with this editor's fields
    opened_at: ClassVar[str]  # spec step that opens it, reported when a step needs it unopened

    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._tab: EditorTab | None = None

    @property
    def tab(self) -> EditorTab:
        if self._tab is None:
            raise ManualReviewRequired(
                self.opened_at, ReviewReason.UI_ELEMENT_NOT_FOUND, f"{type(self).__name__}: editor not open"
            )
        return self._tab

    def activate(self) -> None:
        """Bring this run's editor tab back to the front (never a same-titled leftover draft)."""
        self._ctx.workbench.activate(self.tab)

    def save(self) -> None:
        """Toolbar Save, once; returns when the editor is no longer dirty."""
        self._ctx.workbench.save(self.tab)

    def _pane(self) -> Any:
        return self._ctx.workbench.pane(self.tab)

    def _field(self, key: str, scope: Any | None = None) -> Any:
        return self._ctx.find(self.section, key, scope=scope if scope is not None else self._pane())

    def _word(self, key: str) -> str:
        """A UI word from selectors.yaml (an option text, a tab title)."""
        return str(self._ctx.selectors.value(self.section, key))
