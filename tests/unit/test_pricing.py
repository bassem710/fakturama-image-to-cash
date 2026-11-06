from decimal import Decimal as D

from imagetocash.domain.pricing import gross_master_price, line_net_price, round_money


def test_gross_master_price_applies_vat_and_rounds_half_up() -> None:
    assert gross_master_price(D("10.00"), D("19")) == D("11.90")
    assert gross_master_price(D("0.125"), D("0")) == D("0.13")
    assert gross_master_price(D("12.34"), D("7")) == D("13.20")  # 13.2038 -> 13.20


def test_gross_master_price_ignores_line_discount_by_design() -> None:
    # Spec 3.9: the transaction-line discount must not reach the Product master price.
    assert gross_master_price(D("100"), D("19")) == D("119.00")


def test_line_net_price_applies_quantity_and_discount() -> None:
    assert line_net_price(D("3"), D("19.99"), D("10")) == D("53.97")  # 53.973
    assert line_net_price(D("2"), D("5.00"), D("0")) == D("10.00")


def test_round_money_is_commercial_rounding() -> None:
    assert round_money(D("2.345")) == D("2.35")
    assert round_money(D("-2.345")) == D("-2.35")
