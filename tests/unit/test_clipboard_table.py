from imagetocash.automation.clipboard_table import parse_rows


def test_parse_natable_copy() -> None:
    text = "true\tTax-free\tFree of Tax\t0.0\r\nfalse\tVAT 19%\tnull\t0.19\r\n"
    assert parse_rows(text) == [["true", "Tax-free", "Free of Tax", "0.0"], ["false", "VAT 19%", "", "0.19"]]
