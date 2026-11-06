"""Data > Documents (spec 1.2.1, 4.5, 5.5). Columns: an icon-only type column, Document, Date, Name,
Cust.Ref., State, Total, Printed. The copy gives raw values, translated here into what the UI shows:
the type from the document number prefix, the state from its icon key, the date as ISO."""

from __future__ import annotations

from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.master_data import MasterDataListScreen
from imagetocash.fakturama.values import iso_date


class DocumentsListScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._list = MasterDataListScreen(ctx, "documents", "documents")
        self._date_format = ctx.ui_date_parse_format
        self._type_by_prefix = dict(ctx.selectors.value("lists", "document_type_by_prefix"))
        self._state_by_key = dict(ctx.selectors.value("lists", "document_state_by_key"))

    def open(self) -> None:
        self._list.open()

    def rows_for_reference(self, customer_reference: str) -> list[dict[str, str]]:
        rows = self._list.search(customer_reference)
        for row in rows:
            row["date"] = iso_date(row.get("date", ""), self._date_format)
            if "state" in row:
                row["state"] = self._state_by_key.get(row["state"].strip(), row["state"])
            number = row.get("number", "").strip().upper()
            row["type"] = next((t for p, t in self._type_by_prefix.items() if number.startswith(p)), "")
        return rows
