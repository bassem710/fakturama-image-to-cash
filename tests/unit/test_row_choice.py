"""Which visible row the pointer exception double-clicks (by content, never by copy index)."""

from imagetocash.automation.ocr_table import OcrTableRow
from imagetocash.fakturama.row_choice import rows_showing, same_cell

TITLES = {"number": "No.", "company": "Company", "name": "Name", "value": "Value"}


def test_row_is_found_by_its_key_column_not_its_position() -> None:
    rows = [OcrTableRow({"No.": "7", "Company": "Other"}, 10), OcrTableRow({"No.": "12", "Company": "N..."}, 30)]
    assert [r.middle_y for r in rows_showing(rows, TITLES, {"number": "12"}, ["number"])] == [30]


def test_ocr_percent_and_folded_characters_match() -> None:
    assert same_cell("19.00 0/0", "19%")
    assert same_cell("CHR-ERG-OI", "CHR-ERG-01")


def test_codes_never_compare_as_numbers() -> None:
    assert not same_cell("A-100", "B-100")
    assert not same_cell("7", "17")
