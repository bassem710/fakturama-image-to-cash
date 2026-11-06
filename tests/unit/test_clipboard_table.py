from imagetocash.automation.clipboard_table import parse_rows


def test_parse_natable_copy() -> None:
    text = "true\tTax-free\tFree of Tax\t0.0\r\nfalse\tVAT 19%\tnull\t0.19\r\n"
    assert parse_rows(text) == [["true", "Tax-free", "Free of Tax", "0.0"], ["false", "VAT 19%", "", "0.19"]]


def test_items_grid_vat_record_reads_as_percent() -> None:
    from imagetocash.fakturama.screen_context import _fraction_to_percent

    record = "VAT taxValue: [0.19] salesEqualizationTax: [null] name: [VAT 19%] id: [5]"
    assert _fraction_to_percent(record) == "19%"
    assert _fraction_to_percent("0.07") == "7%"


def test_items_grid_discount_is_a_negative_fraction() -> None:
    from imagetocash.fakturama.screen_context import _fraction_to_percent

    assert _fraction_to_percent("-0.1") == "10%"


def test_documents_list_reads_java_date_text() -> None:
    from imagetocash.fakturama.screens.documents_list import DocumentsListScreen

    screen = DocumentsListScreen.__new__(DocumentsListScreen)
    screen._date_format = "%b %d, %Y"
    assert screen._iso_date("Tue Jul 14 00:00:00 EET 2026") == "2026-07-14"
    assert screen._iso_date("2026-07-14") == "2026-07-14"
