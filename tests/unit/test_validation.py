"""Extraction validation: line totals, net/VAT/gross and payment date must add up."""

import dataclasses
from decimal import Decimal as D

import pytest

from imagetocash.domain.models import OrderDocument, SourceTotals
from imagetocash.domain.pricing import gross_master_price
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.domain.validation import (
    ensure_order_is_consistent,
    ensure_required_fields,
    find_inconsistencies,
    required_fields_missing,
)


def test_sample_order_from_pdf_is_consistent(northstar_order: OrderDocument) -> None:
    assert find_inconsistencies(northstar_order) == []
    ensure_order_is_consistent(northstar_order)


def test_sample_order_master_prices(northstar_order: OrderDocument) -> None:
    chair, mat = northstar_order.items
    assert gross_master_price(chair.unit_net_price, chair.vat_percent) == D("297.50")
    assert gross_master_price(mat.unit_net_price, mat.vat_percent) == D("47.60")


def test_sample_order_has_separate_delivery_address(northstar_order: OrderDocument) -> None:
    assert not northstar_order.debtor.billing_equals_delivery


def test_tampered_line_total_stops_at_1_1(northstar_order: OrderDocument) -> None:
    bad_line = dataclasses.replace(northstar_order.items[0], source_line_total=D("500.00"))
    tampered = dataclasses.replace(northstar_order, items=(bad_line, northstar_order.items[1]))
    with pytest.raises(ManualReviewRequired) as stop:
        ensure_order_is_consistent(tampered)
    assert stop.value.spec_step == "1.1"
    assert stop.value.reason is ReviewReason.TOTALS_MISMATCH
    assert "CHR-ERG-01" in stop.value.detail


def test_wrong_gross_total_is_reported(northstar_order: OrderDocument) -> None:
    tampered = dataclasses.replace(
        northstar_order, totals=SourceTotals(net=D("570.00"), vat=D("108.30"), gross=D("700.00"))
    )
    assert any("gross total" in p for p in find_inconsistencies(tampered))


def test_paid_without_date_is_reported(northstar_order: OrderDocument) -> None:
    unpaid_date = dataclasses.replace(northstar_order.payment, payment_date=None)
    tampered = dataclasses.replace(northstar_order, payment=unpaid_date)
    assert any("payment date" in p for p in find_inconsistencies(tampered))


def _blank(order: OrderDocument, field: str) -> OrderDocument:
    """`order` with one extracted value left blank, as if the image did not show it."""
    debtor = order.debtor
    if field == "customer name":
        return dataclasses.replace(order, debtor=dataclasses.replace(debtor, company="", first_name="", last_name=" "))
    if field in ("billing country", "delivery city"):
        which, attr = field.split()
        address = dataclasses.replace(getattr(debtor, f"{which}_address"), **{attr: ""})
        return dataclasses.replace(order, debtor=dataclasses.replace(debtor, **{f"{which}_address": address}))
    first = dataclasses.replace(order.items[0], **{field: ""})
    return dataclasses.replace(order, items=(first, *order.items[1:]))


def test_sample_order_has_every_required_field(northstar_order: OrderDocument) -> None:
    assert required_fields_missing(northstar_order) == []
    ensure_required_fields(northstar_order)


@pytest.mark.parametrize(
    ("field", "reported"),
    [
        ("customer name", "Company or customer name"),
        ("billing country", "billing street / ZIP / City / Country"),
        ("delivery city", "delivery street / ZIP / City / Country"),
        ("sku", "item 1 SKU"),
        ("description", "item 1 description"),
    ],
)
def test_blank_required_field_stops_at_1_2(northstar_order: OrderDocument, field: str, reported: str) -> None:
    order = _blank(northstar_order, field)
    assert required_fields_missing(order) == [reported]
    with pytest.raises(ManualReviewRequired) as stop:
        ensure_required_fields(order)
    assert stop.value.spec_step == "1.2"
    assert stop.value.reason is ReviewReason.EXTRACTION_INVALID
    assert reported in stop.value.detail
