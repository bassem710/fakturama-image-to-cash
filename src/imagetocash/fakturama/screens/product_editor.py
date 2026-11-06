"""New product editor (spec 3.7-3.11). Labels from the spec; confirm with `imagetocash inspect`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from imagetocash.automation.input import combo_options, read_value, select_combo_option, set_and_verify
from imagetocash.domain.models import LineItem
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import parse_amount
from imagetocash.fakturama.screen_context import EditorTab, ScreenContext

S = "product_editor"


def _amount_text(text: str) -> str:
    try:
        return f"{parse_amount(text):.2f}"
    except Exception:
        return text.strip()


class ProductEditorScreen:
    def __init__(self, ctx: ScreenContext) -> None:
        self._ctx = ctx
        self._tab: EditorTab | None = None

    def open_new_product(self) -> None:
        self._ctx.session.bring_to_front()
        before = self._ctx.tab_snapshot()
        self._ctx.find("main", "new_product").click_input()  # navigation entry: no Invoke pattern
        self._tab = self._ctx.wait_for_new_tab(before)

    def vat_options(self) -> list[str]:
        return [o.strip() for o in combo_options(self._field("vat"))]

    def fill(self, item: LineItem, gross_price: Decimal, vat_name: str) -> None:
        set_and_verify(self._field("item_number"), item.sku, spec_step="3.8", field_name="Item Number")
        set_and_verify(self._field("name"), item.description, spec_step="3.8", field_name="Name")
        set_and_verify(self._field("description"), item.description, spec_step="3.8", field_name="Description")
        # VAT first: Fakturama recomputes the gross price when the VAT changes.
        select_combo_option(self._field("vat"), vat_name, spec_step="3.10", field_name="VAT")
        set_and_verify(
            self._field("price_gross"),
            f"{gross_price:.2f}",
            spec_step="3.9",
            field_name="Price (gross)",
            normalize=_amount_text,
        )
        for key, label in (("cost_price", "cost price (net)"), ("stock", "Stock")):
            field = self._field(key)
            if _amount_text(read_value(field)) != "0.00":
                set_and_verify(field, "0.00", spec_step="3.10", field_name=label, normalize=_amount_text)
        # Category, GTIN, supplier code, allowance, picture, user field 1: left untouched (3.10).

    def save(self) -> None:
        self._ctx.save_editor(self._require_tab())

    def _require_tab(self) -> EditorTab:
        if self._tab is None:
            raise ManualReviewRequired("3.7", ReviewReason.UI_ELEMENT_NOT_FOUND, "no Product editor opened")
        return self._tab

    def _field(self, key: str) -> Any:
        return self._ctx.find(S, key, scope=self._ctx.editor_pane(self._require_tab()))
