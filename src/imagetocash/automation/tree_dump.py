"""Discovery aid: print a UIA subtree with control types, names, ids, patterns and rectangles.
Used by `imagetocash inspect` to build and re-check docs/control-map.md."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

PATTERN_PROBES = ("value", "invoke", "toggle", "selection_item", "expand_collapse", "selection", "grid")


def supported_patterns(element: Any) -> list[str]:
    names = []
    for pattern in PATTERN_PROBES:
        try:
            getattr(element, f"iface_{pattern}")
            names.append(pattern)
        except Exception:  # pywinauto raises NoPatternInterfaceError (or COMError) when absent
            continue
    return names


def describe(element: Any) -> str:
    info = element.element_info
    rect = element.rectangle()
    return (
        f"{info.control_type} name={info.name!r} cls={info.class_name} id={info.automation_id!r} "
        f"{supported_patterns(element)} ({rect.left},{rect.top},{rect.right},{rect.bottom})"
    )


def walk(element: Any, max_depth: int = 25, depth: int = 0) -> Iterator[tuple[int, Any]]:
    yield depth, element
    if depth >= max_depth:
        return
    for child in element.children():
        yield from walk(child, max_depth, depth + 1)


def dump_tree(element: Any, max_depth: int = 25) -> str:
    return "\n".join("  " * depth + describe(node) for depth, node in walk(element, max_depth))
