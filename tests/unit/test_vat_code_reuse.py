"""3.5: a VAT rate this run saved at 3.6 is not reopened to read its code; anything else is."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from imagetocash.fakturama.screens.master_data import MasterDataListScreen, VatListScreen


def _screen(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, str]], saved: dict[str, str]) -> Any:
    monkeypatch.setattr(MasterDataListScreen, "search", lambda self, text: [dict(r) for r in rows])
    screen = object.__new__(VatListScreen)
    screen._ctx = SimpleNamespace(saved_vat_codes=saved)  # type: ignore[assignment]
    screen.opened = []
    screen._read_code = lambda record: screen.opened.append(record["value"]) or "S (from editor)"
    return screen


def test_rate_saved_this_run_is_not_reopened(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = _screen(monkeypatch, [{"name": "VAT 19%", "value": "19%"}], {"VAT 19%": "S (Standard rate)"})
    assert screen.search("VAT 19%")[0]["code"] == "S (Standard rate)"
    assert screen.opened == []


def test_unknown_rate_is_read_from_its_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = _screen(monkeypatch, [{"name": "VAT 19%", "value": "19%"}], {})
    assert screen.search("VAT 19%")[0]["code"] == "S (from editor)"
    assert screen.opened == ["19%"]


def test_two_rates_of_that_name_are_both_read(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"name": "VAT 19%", "value": "19%"}, {"name": "VAT 19%", "value": "7%"}]
    screen = _screen(monkeypatch, rows, {"VAT 19%": "S (Standard rate)"})
    assert [r["code"] for r in screen.search("VAT 19%")] == ["S (from editor)"] * 2
    assert screen.opened == ["19%", "7%"]
