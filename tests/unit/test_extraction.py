"""Extraction parsing: amounts, dates and the mapping of a saved extraction to the order model."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from tests.conftest import make_northstar_order

from imagetocash.domain.review import ManualReviewRequired
from imagetocash.extraction.extractors import SavedJsonOrderExtractor
from imagetocash.extraction.mapper import to_order_document
from imagetocash.extraction.parsing import ParseError, parse_amount, parse_date

FIXTURE = Path(__file__).parent.parent / "fixtures" / "northstar_extracted.json"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("EUR 570.00", D("570.00")),
        ("1.234,56", D("1234.56")),
        ("1,234.56", D("1234.56")),
        ("10%", D("10")),
        ("19 %", D("19")),
        ("-3,5", D("-3.5")),
        ("1.234", D("1234")),
        ("250", D("250")),
        ("0,125", D("0.125")),  # a zero integer part is never a thousands group
        ("1.234,567", D("1234.567")),  # both separators: the last one is the decimal point
        ("1234.567", D("1234.567")),  # four leading digits are not a thousands group
        ("1.234.567", D("1234567")),
        ("12.", D("12")),
    ],
)
def test_parse_amount(text: str, expected: D) -> None:
    assert parse_amount(text) == expected


def test_parse_amount_rejects_text_without_number() -> None:
    with pytest.raises(ParseError):
        parse_amount("n/a")


def test_parse_date_formats() -> None:
    assert parse_date("2026-07-14") == date(2026, 7, 14)
    assert parse_date("14.07.2026") == date(2026, 7, 14)
    with pytest.raises(ParseError):
        parse_date("July 14th")


def test_saved_extraction_maps_to_the_expected_order() -> None:
    extracted = SavedJsonOrderExtractor(FIXTURE).extract(Path("ignored.png"))
    assert to_order_document(extracted) == make_northstar_order()


def test_unparseable_amount_stops_at_1_1() -> None:
    extracted = SavedJsonOrderExtractor(FIXTURE).extract(Path("ignored.png"))
    broken = extracted.model_copy(update={"net_total": "unreadable"})
    with pytest.raises(ManualReviewRequired) as stop:
        to_order_document(broken)
    assert stop.value.spec_step == "1.1"
