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


def test_truncated_cell_matches_by_its_visible_prefix() -> None:
    assert same_cell("Northstar Offic...", "Northstar Office GmbH")
    assert not same_cell("No...", "Northstar Office GmbH")  # too short to tell records apart
    assert not same_cell("Northstar Other...", "Northstar Office GmbH")


def test_ocr_variants_of_the_ellipsis_count_as_truncation() -> None:
    for shown in ("Ergonomic Des..", "Ergonomic Des. . .", "Ergonomic Des…"):
        assert same_cell(shown, "Ergonomic Desk Chair")
    assert not same_cell("Ergonomic Des.", "Ergonomic Desk Chair")  # one dot is not an ellipsis
