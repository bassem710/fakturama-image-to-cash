"""The whole spec flow (1.1 -> 5.7) against the in-memory Fakturama."""

import json
from pathlib import Path

import pytest
from tests.workflow.fakes import FakeDb, FakeFakturama

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.extraction.extractors import SavedJsonOrderExtractor
from imagetocash.extraction.schema import ExtractedOrder
from imagetocash.workflow.runner import ExitCode, ImageToCashRunner, RunOutcome

FIXTURE = Path(__file__).parent.parent / "fixtures" / "northstar_extracted.json"


def run_once(tmp_path: Path, ui: FakeFakturama, extraction: Path = FIXTURE, name: str = "run") -> RunOutcome:
    evidence = EvidenceRecorder(tmp_path / name)
    runner = ImageToCashRunner(SavedJsonOrderExtractor(extraction), lambda: ui, evidence)
    return runner.run(Path("order.png"))


def steps_of(tmp_path: Path, name: str = "run") -> list[str]:
    lines = (tmp_path / name / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["spec_step"] for line in lines]


def write_variant(tmp_path: Path, **changes: object) -> Path:
    data = json.loads(FIXTURE.read_text(encoding="utf-8")) | changes
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(ExtractedOrder.model_validate(data).model_dump()), encoding="utf-8")
    return path


def test_clean_workspace_creates_master_data_and_finishes(tmp_path: Path) -> None:
    ui = FakeFakturama()
    outcome = run_once(tmp_path, ui)

    assert outcome.exit_code is ExitCode.DONE, outcome.message
    db = ui.db
    assert [d["company"] for d in db.debtors] == ["Northstar Office GmbH"]
    assert [p["sku"] for p in db.products] == ["CHR-ERG-01", "MAT-DESK-02"]
    assert [p["gross"] for p in db.products] == ["297.50", "47.60"]  # spec 3.9, no line discount
    assert db.vats == [{"name": "VAT 19%", "value": "19%", "code": "S (Standard rate)"}]  # created once, reused
    assert db.payment_methods == [{"name": "Bank Transfer", "code": "Credit transfer"}]  # spec 2.10.4
    assert [(d["type"], d["state"], d["total"]) for d in db.documents] == [
        ("Order", "open", "$678.30"),
        ("Invoice", "paid", "$678.30"),
    ]
    assert ui.invoice.payment == {"paid": "true", "date": "2026-07-18", "value": "$678.30", "method": "Bank Transfer"}
    steps = steps_of(tmp_path)
    assert steps[:8] == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"]
    assert "2.12" in steps and "2.4" not in steps  # creation branch, then reselect from the Order
    assert steps.count("3.6") == 1 and steps.count("3.12") == 2  # VAT created once, both products reselected
    assert steps[-1] == "5.7"
    assert "order.follow_up_invoice" in db.calls  # 4.6 uses the follow-up area


def test_second_run_selects_existing_master_data(tmp_path: Path) -> None:
    ui = FakeFakturama()
    run_once(tmp_path, ui, name="first")
    outcome = run_once(tmp_path, ui, name="second")

    assert outcome.exit_code is ExitCode.DONE, outcome.message
    db = ui.db
    assert len(db.debtors) == 1 and len(db.products) == 2 and len(db.vats) == 1 and len(db.payment_methods) == 1
    # A second Order + Invoice is expected (the spec has no duplicate-order guard); 4.5/5.5 find
    # the rows by their generated numbers, so the earlier documents do not confuse the checks.
    assert [d["number"] for d in db.documents] == ["PO000001", "IN000001", "PO000002", "IN000002"]
    steps = steps_of(tmp_path, "second")
    assert "2.4" in steps and "2.5" not in steps and "3.4" not in steps


def test_ambiguous_debtor_stops_at_2_3(tmp_path: Path) -> None:
    ui = FakeFakturama()
    run_once(tmp_path, ui, name="first")
    ui.db.debtors.append(dict(ui.db.debtors[0]))  # duplicate Debtor
    outcome = run_once(tmp_path, ui, name="second")
    assert outcome.exit_code is ExitCode.MANUAL_REVIEW
    assert outcome.message.startswith("[2.3] ambiguous_match")


def test_conflicting_debtor_stops_instead_of_creating_a_duplicate(tmp_path: Path) -> None:
    db = FakeDb(
        debtors=[
            {
                "company": "Northstar Office GmbH",
                "first_name": "Marta",
                "last_name": "Klein",
                "zip": "20095",
                "city": "Hamburg",
            }
        ]
    )
    outcome = run_once(tmp_path, FakeFakturama(db))
    assert outcome.message.startswith("[2.3] conflicting_match")
    assert "debtor.new" not in db.calls


def test_product_dialog_applying_a_wrong_single_hit_stops_at_3_3(tmp_path: Path) -> None:
    # 'Select a product' applies its only filter hit by itself; that hit merely contains the SKU.
    db = FakeDb(products=[{"sku": "CHR-ERG-010", "name": "Other chair", "gross": "100.00", "vat": "19%"}])
    outcome = run_once(tmp_path, FakeFakturama(db))
    assert outcome.exit_code is ExitCode.MANUAL_REVIEW
    assert outcome.message.startswith("[3.3] conflicting_match")
    assert "product.new" not in db.calls


def test_conflicting_vat_definition_stops_at_3_5(tmp_path: Path) -> None:
    db = FakeDb(vats=[{"name": "VAT 19%", "value": "19%", "code": "Z (Zero rated goods)"}])
    outcome = run_once(tmp_path, FakeFakturama(db))
    assert outcome.message.startswith("[3.5] conflicting_match")


def test_unmapped_payment_method_stops_before_creating_it(tmp_path: Path) -> None:
    ui = FakeFakturama()
    outcome = run_once(tmp_path, ui, write_variant(tmp_path, payment_method="PayPal"))
    assert outcome.message.startswith("[2.10.4]")
    assert "payment_methods.new" not in ui.db.calls


def test_unpaid_order_leaves_paid_clear(tmp_path: Path) -> None:
    ui = FakeFakturama()
    outcome = run_once(tmp_path, ui, write_variant(tmp_path, paid_status="UNPAID", payment_date=None))
    assert outcome.exit_code is ExitCode.DONE, outcome.message
    assert ui.invoice.payment["paid"] == "false" and not ui.invoice.payment.get("date")
    assert ui.db.documents[-1]["state"] == "open"


def test_inconsistent_extraction_never_touches_fakturama(tmp_path: Path) -> None:
    connected: list[bool] = []

    def connect() -> FakeFakturama:
        connected.append(True)
        return FakeFakturama()

    evidence = EvidenceRecorder(tmp_path / "run")
    variant = write_variant(tmp_path, gross_total="EUR 700.00")
    outcome = ImageToCashRunner(SavedJsonOrderExtractor(variant), connect, evidence).run(Path("x.png"))
    assert outcome.exit_code is ExitCode.MANUAL_REVIEW and outcome.message.startswith("[1.1]")
    assert connected == []
    assert (tmp_path / "run" / "report.md").exists()


@pytest.mark.parametrize("missing", ["external_reference", "payment_method"])
def test_missing_required_field_stops_at_1_2(tmp_path: Path, missing: str) -> None:
    outcome = run_once(tmp_path, FakeFakturama(), write_variant(tmp_path, **{missing: ""}))
    assert outcome.message.startswith(("[1.2]", "[1.1]"))
