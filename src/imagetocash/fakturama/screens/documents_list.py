"""Data > Documents (spec 4.5, 5.5). Columns: an icon-only type column, Document, Date, Name,
Cust.Ref., State, Total, Printed. The type is derived from the document number prefix."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from imagetocash.fakturama.screens.master_data import MasterDataListScreen


class DocumentsListScreen:
    def __init__(
        self, list_screen: MasterDataListScreen, date_parse_format: str, type_by_prefix: Mapping[str, str]
    ) -> None:
        self._list = list_screen
        self._date_format = date_parse_format
        self._type_by_prefix = dict(type_by_prefix)

    def open(self) -> None:
        self._list.open()

    def rows_for_reference(self, customer_reference: str) -> list[dict[str, str]]:
        rows = self._list.search(customer_reference)
        for row in rows:
            row["date"] = self._iso_date(row.get("date", ""))
            number = row.get("number", "").strip().upper()
            row["type"] = next((t for p, t in self._type_by_prefix.items() if number.startswith(p)), "")
        return rows

    def _iso_date(self, text: str) -> str:
        """UI format (OCR fallback) or the raw clipboard value (ISO date/time, or Java's Date text)."""
        value = text.strip()
        for fmt in (self._date_format, "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%a %b %d %H:%M:%S %Z %Y"):
            try:
                return (
                    datetime.strptime(value if "%H" in fmt or len(value) <= 12 else value[:10], fmt).date().isoformat()
                )
            except ValueError:
                continue
        return value
