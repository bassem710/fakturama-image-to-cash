"""Extraction validation: line totals, net/VAT/gross and payment date must add up."""

import dataclasses
from decimal import Decimal as D

import pytest

from imagetocash.domain.models import OrderDocument, SourceTotals
from imagetocash.domain.pricing import gross_master_price
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.domain.validation import ensure_order_is_consistent, find_inconsistencies


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
