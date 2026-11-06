"""Validated, normalized order data (the output of spec 1.1-1.2). Pure data, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from imagetocash.domain.matching import normalize_text


@dataclass(frozen=True)
class Address:
    name: str  # first printed line, e.g. "Northstar Office GmbH" or "Northstar Office Warehouse"
    street: str
    zip_code: str
    city: str
    country: str
    address_specification: str | None = None
    district: str | None = None

    def same_place_as(self, other: Address) -> bool:
        fields = ("name", "street", "zip_code", "city", "country", "address_specification", "district")
        return all(normalize_text(getattr(self, f)) == normalize_text(getattr(other, f)) for f in fields)


@dataclass(frozen=True)
class Debtor:
    company: str
    first_name: str
    last_name: str
    alias: str
    email: str
    telephone: str
    billing_address: Address
    delivery_address: Address
    salutation: str | None = None
    source_customer_id: str | None = None  # printed on the image; spec 2.6 keeps Fakturama's own ID

    @property
    def billing_equals_delivery(self) -> bool:
        return self.billing_address.same_place_as(self.delivery_address)

    @property
    def search_text(self) -> str:
        """Spec 2.2: search using the Company, or the customer name when there is no company."""
        return self.company or f"{self.first_name} {self.last_name}".strip()

    def match_record(self) -> dict[str, str]:
        """The fields spec 2.3 compares in the address selector."""
        return {
            "company": self.company,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "zip": self.billing_address.zip_code,
            "city": self.billing_address.city,
        }


@dataclass(frozen=True)
class PaymentInfo:
    method: str
    paid_status: str
    payment_date: date | None

    @property
    def is_paid(self) -> bool:
        return normalize_text(self.paid_status) == "paid"


@dataclass(frozen=True)
class LineItem:
    position: int
    sku: str
    description: str
    quantity: Decimal
    unit_net_price: Decimal
    vat_percent: Decimal
    discount_percent: Decimal
    source_line_total: Decimal


@dataclass(frozen=True)
class SourceTotals:
    net: Decimal
    vat: Decimal
    gross: Decimal


@dataclass(frozen=True)
class OrderDocument:
    order_date: date
    external_reference: str
    currency: str
    debtor: Debtor
    payment: PaymentInfo
    items: tuple[LineItem, ...]
    totals: SourceTotals
    order_discount_percent: Decimal = Decimal(0)  # spec 4.2: only when the image supplies it
    shipping_net: Decimal = Decimal(0)
