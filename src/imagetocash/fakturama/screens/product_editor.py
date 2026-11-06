"""New product editor (spec 3.7-3.11)."""

from __future__ import annotations

from decimal import Decimal

from imagetocash.automation.input import combo_options, read_value, select_combo_option, set_and_verify
from imagetocash.domain.models import LineItem
from imagetocash.fakturama.screen_context import ScreenContext
from imagetocash.fakturama.screens.base_editor import EditorScreen
from imagetocash.fakturama.values import is_zero, money_text


class ProductEditorScreen(EditorScreen):
    section = "product_editor"
    opened_at = "3.7"

    def __init__(self, ctx: ScreenContext) -> None:
        super().__init__(ctx)
        self._vat_options: list[str] = []

    def open_new_product(self) -> None:
        self._tab = self._ctx.workbench.open_new("new_product", "new_product_toolbar")
        self._vat_options = []

    def vat_options(self) -> list[str]:
        """3.7 check: the VAT rate is offered in the dropdown (read once, reused by fill())."""
        self._vat_options = combo_options(self._field("vat"))
        return [o.strip() for o in self._vat_options]

    def fill(self, item: LineItem, gross_price: Decimal, vat_name: str) -> None:
        set_and_verify(self._field("item_number"), item.sku, spec_step="3.8", field_name="Item Number")
        set_and_verify(self._field("name"), item.description, spec_step="3.8", field_name="Name")
        set_and_verify(self._field("description"), item.description, spec_step="3.8", field_name="Description")
        # VAT first: Fakturama recomputes the gross price when the VAT changes.
        select_combo_option(
            self._field("vat"), vat_name, spec_step="3.10", field_name="VAT", options=self._vat_options or None
        )
        set_and_verify(
            self._field("price_gross"),
            f"{gross_price:.2f}",
            spec_step="3.9",
            field_name="Price (gross)",
            normalize=money_text,
        )
        for key, label in (("cost_price", "cost price (net)"), ("stock", "Stock")):
            field = self._field(key)
            if not is_zero(read_value(field)):
                set_and_verify(field, "0.00", spec_step="3.10", field_name=label, normalize=money_text)
        # Category, GTIN, supplier code, allowance, picture, user field 1: left untouched (3.10).
