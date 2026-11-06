"""Grounding without coordinates: each locator finds a UIA element *relative to a scope element*.

Strategies, tried in order by LocatorChain (Chain of Responsibility; add a strategy = add a class):
1. ByProperties          - UIA control type / name / automation id / class name
2. ByLabel               - unnamed SWT field: find its label, take the next field of the wanted type
3. ByOrderInLabeledGroup - unnamed icons: Nth element (top-to-bottom) inside the label's container
OCR-based grounding for custom-drawn widgets lives in screen_ocr.py / ocr_table.py and is always
bounded by a rectangle that one of these locators returned.

Speed (measured on Fakturama's SWT tree): a UIA FindAll walks the whole subtree (~0.4 s on the
main window) whatever the condition, while FindFirst stops at the first match (~0.01 s). So
named lookups use `find_first`, and `CachedScope` reads each element's properties at most once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.uia_defines import IUIA
from pywinauto.uia_element_info import UIAElementInfo

from imagetocash.automation.waiting import WaitTimeout, wait_until


class UiElementNotFound(LookupError):
    pass


class Locator(Protocol):
    @property
    def description(self) -> str: ...

    def find(self, scope: Any) -> Any | None: ...


def _matches(
    element: Any, control_type: str | None, name: str | None, auto_id: str | None, class_name: str | None
) -> bool:
    info = element.element_info
    return (
        (control_type is None or info.control_type == control_type)
        and (name is None or info.name == name)
        and (auto_id is None or info.automation_id == auto_id)
        and (class_name is None or info.class_name == class_name)
    )


def find_first(scope: Any, *, control_type: str | None = None, name: str | None = None) -> Any | None:
    """The first descendant of `scope` with this control type and/or exact name (native UIA FindFirst:
    stops at the first match instead of walking the whole subtree). None when there is none."""
    if isinstance(scope, CachedScope):
        return ByProperties(control_type=control_type, name=name).find(scope)
    iuia = IUIA()
    try:
        found = scope.element_info.element.FindFirst(
            iuia.tree_scope["descendants"], iuia.build_condition(control_type=control_type, title=name)
        )
    except Exception:
        return None
    return UIAWrapper(UIAElementInfo(found)) if found else None


class CachedScope:
    """ScreenIndex: one walk of a scope's subtree, reused by every locator that searches it, with each
    element's name / type / class read at most once. Behaves like the scope element for locators
    (descendants / children / element_info). Rebuilt by the owner after any UI change."""

    def __init__(self, scope: Any) -> None:
        self._scope = scope
        self._all = [UIAWrapper(info) for info in scope.element_info.descendants(cache_enable=True)]
        self.element_info = scope.element_info

    def descendants(self, control_type: str | None = None) -> list[Any]:
        if control_type is None:
            return list(self._all)
        return [e for e in self._all if e.element_info.control_type == control_type]

    def children(self) -> list[Any]:
        return list(self._scope.children())

    def rectangle(self) -> Any:
        return self._scope.rectangle()


@dataclass(frozen=True)
class ByProperties:
    control_type: str | None = None
    name: str | None = None
    auto_id: str | None = None
    class_name: str | None = None
    name_prefix: str | None = None
    index: int = 0

    @property
    def description(self) -> str:
        parts = [f"{k}={v!r}" for k, v in vars(self).items() if v not in (None, 0)]
        return f"ByProperties({', '.join(parts)})"

    def find(self, scope: Any) -> Any | None:
        if self._plain_name_lookup() and not isinstance(scope, CachedScope):
            return find_first(scope, control_type=self.control_type, name=self.name)
        hits = [
            e
            for e in scope.descendants(control_type=self.control_type)
            if _matches(e, None, self.name, self.auto_id, self.class_name)
            and (self.name_prefix is None or str(e.element_info.name).startswith(self.name_prefix))
        ]
        return hits[self.index] if len(hits) > self.index else None

    def _plain_name_lookup(self) -> bool:
        return self.name is not None and self.index == 0 and not (self.auto_id or self.class_name or self.name_prefix)


@dataclass(frozen=True)
class ByLabel:
    """The first `target_type` element that follows the label in document (tree) order."""

    label: str
    target_type: str = "Edit"
    label_type: str = "Text"
    nth: int = 0  # "First Name Last Name" / "ZIP - City": one label, two fields

    @property
    def description(self) -> str:
        return f"ByLabel({self.label!r} -> {self.target_type} #{self.nth})"

    def find(self, scope: Any) -> Any | None:
        ordered = list(scope.descendants())
        for position, element in enumerate(ordered):
            if _matches(element, self.label_type, self.label, None, None):
                targets = [e for e in ordered[position + 1 :] if e.element_info.control_type == self.target_type]
                return targets[self.nth] if len(targets) > self.nth else None
        return None


@dataclass(frozen=True)
class ByOrderInLabeledGroup:
    """Nth `target_type` child (sorted top-to-bottom, then left-to-right) of the label's container.
    Spec wording: "the upper existing-contact icon beside Addresses" -> label='Addresses', position=0."""

    label: str
    target_type: str = "Image"
    position: int = 0

    @property
    def description(self) -> str:
        return f"ByOrderInLabeledGroup({self.label!r}, {self.target_type} #{self.position})"

    def find(self, scope: Any) -> Any | None:
        label = ByProperties(control_type="Text", name=self.label).find(scope)
        if label is None:
            return None
        siblings = [c for c in label.parent().children() if c.element_info.control_type == self.target_type]
        siblings.sort(key=lambda e: (e.rectangle().top, e.rectangle().left))
        return siblings[self.position] if len(siblings) > self.position else None


@dataclass(frozen=True)
class LocatorChain:
    strategies: tuple[Locator, ...]

    @classmethod
    def of(cls, *strategies: Locator) -> LocatorChain:
        return cls(tuple(strategies))

    @property
    def description(self) -> str:
        return " | ".join(s.description for s in self.strategies)

    def find(self, scope: Any) -> Any | None:
        for strategy in self.strategies:
            element = strategy.find(scope)
            if element is not None:
                return element
        return None


def build_locator(spec: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> Locator:
    """YAML spec -> locator. A list of specs becomes a LocatorChain (first hit wins)."""
    if isinstance(spec, Sequence) and not isinstance(spec, str | Mapping):
        return LocatorChain(tuple(build_locator(s) for s in spec))
    assert isinstance(spec, Mapping)
    kind = spec.get("by", "properties")
    if kind == "properties":
        return ByProperties(
            control_type=spec.get("control_type"),
            name=spec.get("name"),
            auto_id=spec.get("auto_id"),
            class_name=spec.get("class_name"),
            name_prefix=spec.get("name_prefix"),
            index=int(spec.get("index", 0)),
        )
    if kind == "label":
        return ByLabel(
            label=spec["label"],
            target_type=spec.get("target", "Edit"),
            label_type=spec.get("label_type", "Text"),
            nth=int(spec.get("nth", 0)),
        )
    if kind == "order":
        return ByOrderInLabeledGroup(
            label=spec["label"], target_type=spec.get("target", "Image"), position=int(spec.get("position", 0))
        )
    raise ValueError(f"unknown locator kind {kind!r} in {dict(spec)}")


def largest_leaf_pane(scope: Any) -> Any | None:
    """Custom-drawn widgets (NatTable) appear in UIA as a Pane whose only children are scrollbars:
    the biggest such pane in `scope`."""
    leaves = [
        p
        for p in scope.descendants(control_type="Pane")
        if all(c.element_info.control_type == "ScrollBar" for c in p.children())
    ]
    if not leaves:
        return None
    return max(leaves, key=lambda p: p.rectangle().width() * p.rectangle().height())


def locate(scope: Any, locator: Locator, timeout: float = 10.0) -> Any:
    try:
        return wait_until(lambda: locator.find(scope), timeout=timeout, what=locator.description)
    except WaitTimeout as error:
        raise UiElementNotFound(str(error)) from error
