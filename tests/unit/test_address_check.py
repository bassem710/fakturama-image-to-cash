"""Address blocks read from the Order/Invoice must show the image's street, ZIP, city AND country."""

import pytest

from imagetocash.domain.models import Address
from imagetocash.domain.review import ManualReviewRequired
from imagetocash.workflow.checks import address_lines_missing, check_address

BILLING = Address("Northstar Office GmbH", "Friedrichstrasse 88", "10117", "Berlin", "Germany")
SHOWN = "Northstar Office GmbH\r\nMarta Klein\r\nFriedrichstrasse 88\r\nDE-10117 Berlin\r\nGermany"  # read live


def test_the_block_fakturama_shows_passes() -> None:
    assert address_lines_missing(SHOWN, BILLING) == []


def test_a_wrong_country_stops_even_when_street_zip_and_city_match() -> None:
    georgia = SHOWN.replace("DE-", "GE-").replace("Germany", "Georgia")  # the bug found live
    assert address_lines_missing(georgia, BILLING) == ["country"]
    with pytest.raises(ManualReviewRequired, match="country"):
        check_address(georgia, BILLING, "2.13", "Invoice")


def test_country_must_be_a_whole_line_not_a_substring() -> None:
    niger = Address("Shop", "Rue 1", "8001", "Niamey", "Niger")
    assert address_lines_missing("Shop\nRue 1\n8001 Niamey\nNigeria", niger) == ["country"]
    assert address_lines_missing("Shop\nRue 1\n8001 Niamey\n  NIGER ", niger) == []
