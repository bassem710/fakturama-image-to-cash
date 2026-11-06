"""OCR table reader (the fallback for lists): headers, columns, rows from OCR words."""

from imagetocash.automation.ocr_table import build_table
from imagetocash.automation.screen_ocr import OcrWord
from imagetocash.domain.matching import PRODUCT_MATCH_POLICY, ExactMatch


def word(text: str, left: float, top: float, width: float = 40) -> OcrWord:
    return OcrWord(text, left, top, left + width, top + 14)


def test_header_words_merge_into_columns_and_cells_follow_left_edges() -> None:
    words = [
        word("Company", 100, 10, 60),
        word("First", 300, 10, 30),
        word("Name", 334, 10, 34),
        word("Name", 450, 10, 34),
        word("ZIP", 600, 10, 24),
        word("City", 700, 10, 30),
        word("Northstar", 102, 40, 60),
        word("Office", 166, 41, 40),
        word("GmbH", 210, 40, 36),
        word("Marta", 301, 40),
        word("Klein", 452, 41),
        word("10117", 601, 40),
        word("Berlin", 702, 39),
    ]
    table = build_table(words, expected_headers=("Company", "ZIP"))
    assert [title for title, _ in table.columns] == ["Company", "First Name", "Name", "ZIP", "City"]
    assert table.rows[0].cells == {
        "Company": "Northstar Office GmbH",
        "First Name": "Marta",
        "Name": "Klein",
        "ZIP": "10117",
        "City": "Berlin",
    }


def test_ocr_confusables_still_match_the_source_sku() -> None:
    ocr_row = {"sku": "CHR-ERG-OI"}  # what Windows OCR actually read for CHR-ERG-01
    outcome = PRODUCT_MATCH_POLICY.ocr_tolerant().evaluate({"sku": "CHR-ERG-01"}, [ocr_row])
    assert outcome == ExactMatch(ocr_row)
