"""Behaviors found during live calibration against Fakturama 2.2.0."""

from datetime import date
from decimal import Decimal as D

from PIL import Image, ImageDraw

from imagetocash.automation.date_input import _parse
from imagetocash.automation.ocr_table import build_table, find_column_separators
from imagetocash.automation.screen_ocr import OcrWord, ScreenRect
from imagetocash.domain.matching import DEBTOR_MATCH_POLICY, ExactMatch, normalize_percent
from imagetocash.extraction.parsing import parse_amount


def test_ocr_reads_percent_sign_as_0_slash_0() -> None:
    assert normalize_percent("19.00 0/0") == "19"
    assert parse_amount("0.00 0/0") == D("0.00")
    assert parse_amount("19.00 0/0") == D("19.00")


def test_truncated_list_cell_matches_as_prefix() -> None:
    wanted = {
        "company": "Northstar Office GmbH",
        "first_name": "Marta",
        "last_name": "Klein",
        "zip": "10117",
        "city": "Berlin",
    }
    shown = {**wanted, "company": "Northstar Offi..."}
    assert DEBTOR_MATCH_POLICY.ocr_tolerant().evaluate(wanted, [shown]) == ExactMatch(shown)


def test_cdatetime_values_parse_including_half_edited_years() -> None:
    assert _parse("Jul 14, 2026", "%b %d, %Y") == date(2026, 7, 14)
    assert _parse("Dec 20, 27", "%b %d, %Y") == date(27, 12, 20)


def test_grid_lines_define_columns_for_centred_headers() -> None:
    rect = ScreenRect(0, 0, 400, 60)
    image = Image.new("RGB", (400, 60), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    for x in (130, 260):
        draw.line([(x, 0), (x, 59)], fill=(160, 160, 160))
    separators = find_column_separators(image, rect, 2, 22)
    assert [round(s) for s in separators] == [130, 260]

    def word(text: str, left: float, top: float, width: float) -> OcrWord:
        return OcrWord(text, left, top, left + width, top + 14)

    words = [  # centred headers, left-aligned cells (as in 'Select the address')
        word("First", 30, 5, 30),
        word("Name", 64, 5, 32),
        word("Company", 165, 5, 60),
        word("ZIP", 320, 5, 24),
        word("Marta", 4, 35, 36),
        word("Northstar", 134, 35, 60),
        word("Offi...", 198, 35, 40),
        word("10117", 264, 35, 36),
    ]
    table = build_table(words, ("Company",), separators)
    assert table.rows[0].cells == {"First Name": "Marta", "Company": "Northstar Offi...", "ZIP": "10117"}


def test_typed_date_digits_follow_the_display_format() -> None:
    from imagetocash.automation.date_input import typed_digits

    assert typed_digits(date(2026, 7, 14), "%b %d, %Y") == "07142026"  # en_US: Jul 14, 2026
    assert typed_digits(date(2026, 7, 14), "%d.%m.%Y") == "14072026"  # de_DE: 14.07.2026
