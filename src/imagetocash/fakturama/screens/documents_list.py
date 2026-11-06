"""Data > Documents (spec 4.5, 5.5): search box verified; list is custom-drawn (OCR)."""

from __future__ import annotations

from datetime import datetime

from imagetocash.fakturama.screens.master_data import MasterDataListScreen


class DocumentsListScreen:
    def __init__(self, list_screen: MasterDataListScreen, ui_date_format: str) -> None:
        self._list = list_screen
        self._ui_date_format = ui_date_format.replace("{day}", "%d")

    def open(self) -> None:
        self._list.open()

    def rows_for_reference(self, customer_reference: str) -> list[dict[str, str]]:
        rows = self._list.search(customer_reference)
        for row in rows:
            row["date"] = self._iso_date(row.get("date", ""))
        return rows

    def _iso_date(self, text: str) -> str:
        try:
            return datetime.strptime(text.strip(), self._ui_date_format).date().isoformat()
        except ValueError:
            return text
