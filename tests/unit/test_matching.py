"""Record match policies: exact, ambiguous, conflicting, OCR-tolerant comparisons."""

from decimal import Decimal as D

import pytest

from imagetocash.domain.matching import (
    DEBTOR_MATCH_POLICY,
    PRODUCT_MATCH_POLICY,
    VAT_MATCH_POLICY,
    AmbiguousMatch,
    ConflictingMatch,
    ExactMatch,
    NoMatch,
    normalize_percent,
    vat_name_for,
)
from imagetocash.domain.payment_codes import payment_code_for
from imagetocash.domain.review import ManualReviewRequired

WANTED_DEBTOR = {"company": "Acme GmbH", "first_name": "Anna", "last_name": "Meyer", "zip": "10115", "city": "Berlin"}


def test_debtor_exact_match_ignores_case_and_spacing() -> None:
    row = {"company": "ACME  GmbH", "first_name": "anna", "last_name": "Meyer", "zip": "10115", "city": "Berlin "}
    assert DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, [row]) == ExactMatch(row)


def test_debtor_two_exact_rows_is_ambiguous() -> None:
    outcome = DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, [WANTED_DEBTOR, dict(WANTED_DEBTOR)])
    assert isinstance(outcome, AmbiguousMatch)


def test_debtor_same_identity_other_city_is_conflicting_not_new() -> None:
    other_city = {**WANTED_DEBTOR, "city": "Hamburg"}
    assert isinstance(DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, [other_city]), ConflictingMatch)


def test_debtor_exact_row_wins_over_other_branch() -> None:
    other_city = {**WANTED_DEBTOR, "city": "Hamburg"}
    assert DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, [other_city, WANTED_DEBTOR]) == ExactMatch(WANTED_DEBTOR)


def test_unrelated_rows_mean_no_match() -> None:
    stranger = {**WANTED_DEBTOR, "company": "Other AG"}
    assert DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, [stranger]) == NoMatch()
    assert DEBTOR_MATCH_POLICY.evaluate(WANTED_DEBTOR, []) == NoMatch()


def test_product_matches_on_exact_sku_only() -> None:
    rows = [{"sku": "SKU-1"}, {"sku": "SKU-10"}]
    assert PRODUCT_MATCH_POLICY.evaluate({"sku": "SKU-1"}, rows) == ExactMatch({"sku": "SKU-1"})
    assert isinstance(PRODUCT_MATCH_POLICY.evaluate({"sku": "SKU-1"}, [{"sku": "SKU-1"}] * 2), AmbiguousMatch)


@pytest.mark.parametrize(
    ("row", "expected_type"),
    [
        ({"name": "VAT 19%", "value": "19.00 %", "code": "S (Standard rate)"}, ExactMatch),
        ({"name": "VAT 19%", "value": "19", "code": "Z (Zero rated goods)"}, ConflictingMatch),
        ({"name": "VAT 19%", "value": "16", "code": "S"}, ConflictingMatch),
        ({"name": "VAT 7%", "value": "7", "code": "S"}, NoMatch),
    ],
)
def test_vat_policy(row: dict[str, str], expected_type: type) -> None:
    wanted = {"name": "VAT 19%", "value": "19", "code": "S"}
    assert isinstance(VAT_MATCH_POLICY.evaluate(wanted, [row]), expected_type)


def test_vat_name_and_percent_normalization() -> None:
    assert vat_name_for(D("19.00")) == "VAT 19%"
    assert vat_name_for(D("7.5")) == "VAT 7.5%"
    assert normalize_percent("19,0 %") == "19"


def test_payment_code_mapping() -> None:
    assert payment_code_for("Bank Transfer") == "Credit transfer"
    assert payment_code_for("credit card") == "Credit card"
    assert payment_code_for("SEPA Direct Debit") == "SEPA direct debit"
    with pytest.raises(ManualReviewRequired) as stop:
        payment_code_for("PayPal")
    assert stop.value.spec_step == "2.10.4"


def test_row_mentioning_the_identity_blocks_creation() -> None:
    # e.g. the Name column was misread empty but the row clearly is 'VAT 19%'
    row = {"name": "", "description": "VAT 19%", "value": "19.00 %", "code": "S"}
    wanted = {"name": "VAT 19%", "value": "19", "code": "S"}
    assert isinstance(VAT_MATCH_POLICY.ocr_tolerant().evaluate(wanted, [row]), ConflictingMatch)


def test_truncated_cell_outside_the_search_field_is_not_an_exact_match() -> None:
    # 'CHR-ERG-...' may be CHR-ERG-02: only a field the list was filtered on may be truncated
    row = {"sku": "CHR-ERG-..."}
    outcome = PRODUCT_MATCH_POLICY.ocr_tolerant().evaluate({"sku": "CHR-ERG-01"}, [row])
    assert isinstance(outcome, ConflictingMatch)


def test_private_customer_mentioned_in_a_misread_row_blocks_creation() -> None:
    wanted = {"company": "", "first_name": "Marta", "last_name": "Klein", "zip": "10117", "city": "Berlin"}
    misread = {"company": "", "first_name": "", "last_name": "Marta Klein", "zip": "10117", "city": "Berlin"}
    assert isinstance(DEBTOR_MATCH_POLICY.ocr_tolerant().evaluate(wanted, [misread]), ConflictingMatch)
