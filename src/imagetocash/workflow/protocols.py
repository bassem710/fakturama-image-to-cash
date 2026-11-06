"""What the stages need from the UI, one small interface per screen (Interface Segregation).

The workflow depends ONLY on these protocols (Dependency Inversion). The real implementations are
in imagetocash.fakturama.screens; tests use in-memory fakes. Every method either does what its
spec step says and verifies it, or raises ManualReviewRequired / an error.
Rows read from lists are plain dicts keyed by record fields (company, first_name, sku, ...).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from imagetocash.domain.models import Address, Debtor, LineItem

Row = Mapping[str, str]


class SelectionDialogUi(Protocol):
    """'Select the address' / 'Select a product' dialogs opened from the Order (2.2-2.3, 3.3, 3.12)."""

    auto_applied: bool  # True when the dialog applied its only filter hit itself (Select a product does)

    def search(self, text: str) -> Sequence[Row]: ...  # sets the search, waits until the list is stable
    def choose(self, row: Row) -> None: ...  # selects the row and clicks OK
    def cancel(self) -> None: ...


class OrderEditorUi(Protocol):
    def open_new_order(self) -> None: ...  # 1.3
    def activate(self) -> None: ...  # 1.8: bring the same open Order tab back
    def read_document_number(self) -> str: ...  # 1.4
    def set_order_date(self, value: date) -> None: ...  # 1.5
    def set_customer_reference(self, value: str) -> None: ...  # 1.6
    def set_price_mode_net(self) -> None: ...  # 1.7
    def read_vat_mode(self) -> str: ...  # 1.7
    def open_address_selector(self) -> SelectionDialogUi: ...  # 2.1 (upper icon, never the green +)
    def read_address_texts(self) -> dict[str, str]: ...  # 2.4 / 2.13 {"invoice": ..., "delivery": ...}
    def open_product_selector(self) -> SelectionDialogUi: ...  # 3.2
    def read_item_lines(self) -> Sequence[Row]: ...  # sku, quantity, unit_price, vat, discount, price
    def fill_item_line(self, line_index: int, item: LineItem) -> None: ...  # 3.13-3.15
    def ensure_order_level_defaults(self) -> None: ...  # 4.2
    def read_totals(self) -> dict[str, str]: ...  # 4.3 {"net", "vat", "total"}
    def save(self) -> None: ...  # 4.4 toolbar Save, once
    def create_follow_up_invoice(self) -> None: ...  # 4.6 / 4.7


class DebtorEditorUi(Protocol):
    def open_new_debtor(self) -> None: ...  # 2.5
    def fill_identity(self, debtor: Debtor) -> None: ...  # 2.6
    def fill_main_address(self, debtor: Debtor) -> None: ...  # 2.7
    def assign_address_roles(self, debtor: Debtor) -> None: ...  # 2.8
    def fill_miscellaneous(self, debtor: Debtor) -> None: ...  # 2.9
    def payment_methods_offered(self) -> list[str]: ...  # 2.10
    def select_payment_method(self, name: str) -> None: ...  # 2.10 / 2.10.6
    def activate(self) -> None: ...  # return to the open Debtor editor
    def save(self) -> None: ...  # 2.11


class MasterDataListUi(Protocol):
    """Data > terms of payment (2.10.1-2.10.2) and Data > VATs (3.4-3.5)."""

    def open(self) -> None: ...
    def search(self, text: str) -> Sequence[Row]: ...
    def create_new(self) -> None: ...  # the green + at the upper right of the list


class PaymentMethodEditorUi(Protocol):
    def fill(self, name: str, payment_code: str) -> None: ...  # 2.10.3-2.10.5
    def save(self) -> None: ...  # 2.10.6


class VatEditorUi(Protocol):
    def fill(self, name: str, percent: Decimal) -> None: ...  # 3.6
    def save(self) -> None: ...


class ProductEditorUi(Protocol):
    def open_new_product(self) -> None: ...  # 3.7
    def vat_options(self) -> list[str]: ...  # 3.7 check: the VAT is in the dropdown
    def fill(self, item: LineItem, gross_price: Decimal, vat_name: str) -> None: ...  # 3.8-3.10
    def save(self) -> None: ...  # 3.11


class DocumentsListUi(Protocol):
    def open(self) -> None: ...
    def rows_for_reference(self, customer_reference: str) -> Sequence[Row]: ...  # 4.5 / 5.5


class InvoiceEditorUi(Protocol):
    def wait_until_open(self) -> None: ...  # 4.7
    def read_copied_values(self) -> dict[str, str]: ...  # 5.1 cust_ref, order_date, vat_mode, totals
    def read_address_texts(self) -> dict[str, str]: ...
    def read_item_lines(self) -> Sequence[Row]: ...
    def payment_methods_offered(self) -> list[str]: ...  # 5.2
    def select_payment_method(self, name: str) -> None: ...
    def mark_paid(self, payment_date: date, value: Decimal) -> None: ...  # 5.3
    def read_payment_state(self) -> dict[str, str]: ...  # paid, date, value
    def save(self) -> None: ...  # 5.4


class FakturamaUi(Protocol):
    """Everything the run needs, grouped per screen (read-only members, so implementations may
    expose more specific screen types)."""

    @property
    def order(self) -> OrderEditorUi: ...
    @property
    def debtor(self) -> DebtorEditorUi: ...
    @property
    def payment_methods(self) -> MasterDataListUi: ...
    @property
    def payment_method_editor(self) -> PaymentMethodEditorUi: ...
    @property
    def vats(self) -> MasterDataListUi: ...
    @property
    def vat_editor(self) -> VatEditorUi: ...
    @property
    def product_editor(self) -> ProductEditorUi: ...
    @property
    def documents(self) -> DocumentsListUi: ...
    @property
    def invoice(self) -> InvoiceEditorUi: ...


def address_lines_missing(address_text: str, expected: Address) -> list[str]:
    """Which parts of `expected` are not visible in an address block read from the UI."""
    from imagetocash.domain.matching import normalize_ocr_text

    haystack = normalize_ocr_text(address_text)
    parts = {"street": expected.street, "zip": expected.zip_code, "city": expected.city}
    return [label for label, value in parts.items() if normalize_ocr_text(value) not in haystack]
