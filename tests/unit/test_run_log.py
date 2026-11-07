"""Masking and redaction: no order value reaches the console, logs or reports."""

import logging
from pathlib import Path

import pytest

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.automation.run_log import mask, redact, setup_run_logging
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

SECRETS = [
    "Northstar Office GmbH",
    "Friedrichstrasse 88",
    "10117",
    "marta.klein@example.test",
    "+49 30 5550 1420",
    "WEB-2026-0714-A17",
    "678.30",
]


def test_mask_shows_shape_not_value() -> None:
    assert mask("Northstar Office GmbH") == "N***H (21 chars)"
    assert mask("abc") == "*** (3 chars)"
    assert mask("") == "<empty>"


def test_redact_removes_every_sensitive_value() -> None:
    message = (
        "Invoice address on screen 'Northstar Office GmbH\\nFriedrichstrasse 88\\n10117 Berlin' lacks zip; "
        "mail marta.klein@example.test phone +49 30 5550 1420 ref WEB-2026-0714-A17 total 678.30"
    )
    cleaned = redact(message)
    for secret in SECRETS:
        assert secret not in cleaned


def test_step_logs_and_files_are_redacted(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    logger = setup_run_logging(tmp_path)
    logger.propagate = True  # let caplog see it
    evidence = EvidenceRecorder(tmp_path)
    with evidence.spec_step("1.6", "Enter External Reference", expected="WEB-2026-0714-A17") as rec:
        rec.observed = "WEB-2026-0714-A17"
    with pytest.raises(ManualReviewRequired), evidence.spec_step("2.4", "Check addresses"):
        raise ManualReviewRequired(
            "2.4", ReviewReason.VALUE_MISMATCH, "'Northstar Office GmbH' lacks 'Friedrichstrasse 88'"
        )
    evidence.write_report("MANUAL REVIEW at 2.4")
    logging.getLogger("imagetocash").handlers.clear()

    texts = [caplog.text] + [
        p.read_text(encoding="utf-8") for p in tmp_path.glob("*") if p.suffix in {".md", ".jsonl", ".log"}
    ]
    for text in texts:
        for secret in SECRETS:
            assert secret not in text
    assert "1.6" in caplog.text and "OK" in caplog.text
    assert "manual review" in caplog.text


def test_redact_address_repr_with_empty_value_first() -> None:
    # The exact shape that leaked in run #13 (an empty '' before the Address repr).
    message = (
        "Invoice address on screen '' lacks street, zip, city of Address(name='Northstar Office GmbH', "
        "street='Friedrichstrasse 88', zip_code='10117', city='Berlin', country='Germany', "
        "address_specification=None, district=None)"
    )
    cleaned = redact(message)
    for secret in ("Northstar", "Friedrichstrasse", "10117", "Berlin", "Germany"):
        assert secret not in cleaned


def test_step_expected_values_never_reach_the_evidence_files(tmp_path) -> None:
    from imagetocash.automation.evidence import EvidenceRecorder

    recorder = EvidenceRecorder(tmp_path)
    with recorder.spec_step("2.2", "Search by company / customer name", expected="Northstar Office GmbH"):
        pass
    report = recorder.write_report("DONE")
    for written in (tmp_path / "steps.jsonl", report):
        assert "Northstar" not in written.read_text(encoding="utf-8")


MULTI_WORD_ROW = {
    "company": "Northstar Office GmbH",
    "first_name": "Anna Maria",
    "last_name": "Klein",
    "zip": "60311",
    "city": "Frankfurt am Main",
}
TRAILING_WORDS = ("Office", "GmbH", "Maria", "Main")


def test_described_rows_are_masked_whole() -> None:
    from imagetocash.workflow.resolver import _describe

    cleaned = redact(_describe([MULTI_WORD_ROW]))
    for word in TRAILING_WORDS:
        assert word not in cleaned


def test_bare_multi_word_values_are_masked_whole() -> None:
    cleaned = redact("company=Northstar Office GmbH, city=Frankfurt am Main; first_name=Anna Maria")
    for word in TRAILING_WORDS:
        assert word not in cleaned


def test_stop_listing_other_customers_keeps_them_masked_in_evidence(tmp_path: Path) -> None:
    from imagetocash.domain.matching import DEBTOR_MATCH_POLICY
    from imagetocash.workflow.resolver import decide

    evidence = EvidenceRecorder(tmp_path)
    with pytest.raises(ManualReviewRequired), evidence.spec_step("2.3", "Exact match"):
        decide(DEBTOR_MATCH_POLICY, MULTI_WORD_ROW, [MULTI_WORD_ROW, dict(MULTI_WORD_ROW)], "2.3")
    evidence.write_report("MANUAL REVIEW at 2.3")
    for name in ("report.md", "steps.jsonl"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        for word in TRAILING_WORDS:
            assert word not in text
