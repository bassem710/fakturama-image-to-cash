"""Data > Documents (spec 4.5, 5.5). Columns: an icon-only type column, Document, Date, Name,
Cust.Ref., State, Total, Printed. The type is derived from the document number prefix."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime

from imagetocash.fakturama.screens.master_data import MasterDataListScreen

_JAVA_DATE = re.compile(r"[A-Za-z]{3} (?P<md>[A-Za-z]{3} \d{1,2}) \d{2}:\d{2}:\d{2} \S+ (?P<y>\d{4})")


class DocumentsListScreen:
    def __init__(
        self,
        list_screen: MasterDataListScreen,
        date_parse_format: str,
        type_by_prefix: Mapping[str, str],
        state_by_key: Mapping[str, str],
    ) -> None:
        self._list = list_screen
        self._date_format = date_parse_format
        self._type_by_prefix = dict(type_by_prefix)
        self._state_by_key = dict(state_by_key)

    def open(self) -> None:
        self._list.open()

    def rows_for_reference(self, customer_reference: str) -> list[dict[str, str]]:
        rows = self._list.search(customer_reference)
        for row in rows:
            row["date"] = self._iso_date(row.get("date", ""))
            if "state" in row:  # icon key from the copy -> the state word the UI stands for
                row["state"] = self._state_by_key.get(row["state"].strip(), row["state"])
            number = row.get("number", "").strip().upper()
            row["type"] = next((t for p, t in self._type_by_prefix.items() if number.startswith(p)), "")
        return rows

    def _iso_date(self, text: str) -> str:
        """UI format (OCR fallback) or the raw clipboard value (ISO date/time, or Java's Date text)."""
        value = text.strip()
        if java := _JAVA_DATE.fullmatch(value):  # 'Tue Jul 14 00:00:00 EET 2026': %Z rejects 'EET'
            return datetime.strptime(f"{java['md']} {java['y']}", "%b %d %Y").date().isoformat()
        for fmt in (self._date_format, "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return (
                    datetime.strptime(value if "%H" in fmt or len(value) <= 12 else value[:10], fmt).date().isoformat()
                )
            except ValueError:
                continue
        return value
