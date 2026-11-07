"""NatTable clipboard copy parsing (tab-separated raw values, 'null' cells)."""

from imagetocash.automation.clipboard_table import parse_rows


def test_parse_natable_copy() -> None:
    text = "true\tTax-free\tFree of Tax\t0.0\r\nfalse\tVAT 19%\tnull\t0.19\r\n"
    assert parse_rows(text) == [["true", "Tax-free", "Free of Tax", "0.0"], ["false", "VAT 19%", "", "0.19"]]


class _FakeClipboard:
    """In-memory stand-in for the Windows clipboard; Ctrl+C 'copies' `table_text`."""

    def __init__(self, previous: str | None, table_text: str) -> None:
        self.text, self.table_text = previous, table_text

    def get(self) -> str | None:
        return self.text

    def set(self, text: str) -> None:
        self.text = text

    def clear(self) -> None:
        self.text = None

    def keys(self, keys: str, **_: object) -> None:
        if "^c" in keys:
            self.text = self.table_text


def _patch(monkeypatch, clipboard: _FakeClipboard) -> None:
    from imagetocash.automation import clipboard_table

    monkeypatch.setattr(clipboard_table, "_get_text", clipboard.get)
    monkeypatch.setattr(clipboard_table, "_set_text", clipboard.set)
    monkeypatch.setattr(clipboard_table, "_clear", clipboard.clear)
    monkeypatch.setattr(clipboard_table, "focus", lambda _table: True)
    monkeypatch.setattr(clipboard_table.keyboard, "send_keys", clipboard.keys)


def test_users_clipboard_text_is_restored_after_the_copy(monkeypatch) -> None:
    from imagetocash.automation.clipboard_table import copy_table

    clipboard = _FakeClipboard("user text", "Marta\tKlein\r\n")
    _patch(monkeypatch, clipboard)
    assert copy_table(object()) == [["Marta", "Klein"]]
    assert clipboard.text == "user text"


def test_copied_order_data_never_stays_on_an_empty_clipboard(monkeypatch) -> None:
    from imagetocash.automation.clipboard_table import copy_table

    clipboard = _FakeClipboard(None, "Marta\tKlein\r\n")  # empty or non-text before the copy
    _patch(monkeypatch, clipboard)
    assert copy_table(object()) == [["Marta", "Klein"]]
    assert clipboard.text is None
