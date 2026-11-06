"""How Fakturama writes values: field amounts, dates in fields and list copies, copied fractions."""

from imagetocash.fakturama.values import fraction_to_percent, is_zero, iso_date, money_text, number_text, same_number

UI_DATE = "%b %d, %Y"


def test_numbers_compare_by_value_not_by_text() -> None:
    assert number_text("$250.00") == "250"
    assert number_text("0.00 %") == "0"
    assert same_number("2.00", "2") and not same_number("2.5", "25")
    assert is_zero("0,00") and not is_zero("0.01")
    assert number_text("n/a") == "n/a"  # unreadable stays unequal to any number


def test_money_text_has_two_decimals() -> None:
    assert money_text("$1,234.5") == "1234.50"


def test_dates_from_fields_and_list_copies() -> None:
    assert iso_date("Jul 14, 2026", UI_DATE) == "2026-07-14"
    assert iso_date("Tue Jul 14 00:00:00 EET 2026", UI_DATE) == "2026-07-14"  # %Z rejects 'EET'
    assert iso_date("2026-07-14 00:00:00", UI_DATE) == "2026-07-14"
    assert iso_date("someday", UI_DATE) == "someday"


def test_copied_fractions_read_as_percent() -> None:
    assert fraction_to_percent("0.19") == "19%"
    assert fraction_to_percent("VAT taxValue: [0.19] salesEqualizationTax: [null] name: [VAT 19%]") == "19%"
    assert fraction_to_percent("-0.1") == "10%"  # a line discount is stored negative
