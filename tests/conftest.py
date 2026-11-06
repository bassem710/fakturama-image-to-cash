"""Shared fixtures. `northstar_order` is the order printed on page 3 of the take-home PDF."""

from datetime import date
from decimal import Decimal as D

import pytest

from imagetocash.domain.models import Address, Debtor, LineItem, OrderDocument, PaymentInfo, SourceTotals


def make_northstar_order() -> OrderDocument:
    return OrderDocument(
        order_date=date(2026, 7, 14),
        external_reference="WEB-2026-0714-A17",
        currency="EUR",
        debtor=Debtor(
            company="Northstar Office GmbH",
            first_name="Marta",
            last_name="Klein",
            alias="NORTHSTAR-BERLIN",
            email="marta.klein@example.test",
            telephone="+49 30 5550 1420",
            billing_address=Address("Northstar Office GmbH", "Friedrichstrasse 88", "10117", "Berlin", "Germany"),
            delivery_address=Address("Northstar Office Warehouse", "Beusselstrasse 44", "10553", "Berlin", "Germany"),
            source_customer_id="CUST-1007",
        ),
        payment=PaymentInfo(method="Bank Transfer", paid_status="PAID", payment_date=date(2026, 7, 18)),
        items=(
            LineItem(1, "CHR-ERG-01", "Ergonomic Desk Chair", D("2"), D("250.00"), D("19"), D("10"), D("450.00")),
            LineItem(2, "MAT-DESK-02", "Anti-Fatigue Desk Mat", D("3"), D("40.00"), D("19"), D("0"), D("120.00")),
        ),
        totals=SourceTotals(net=D("570.00"), vat=D("108.30"), gross=D("678.30")),
    )


@pytest.fixture
def northstar_order() -> OrderDocument:
    return make_northstar_order()
