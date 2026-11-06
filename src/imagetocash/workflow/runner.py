"""One continuous Order-first run: spec 1.1 -> 5.7. Exit codes: 0 done, 2 manual review, 1 error."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.domain.models import OrderDocument
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.domain.validation import ensure_order_is_consistent
from imagetocash.extraction.extractors import OrderExtractor
from imagetocash.extraction.mapper import to_order_document
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi
from imagetocash.workflow.stage1_open_order import OpenOrderStage
from imagetocash.workflow.stage2_debtor import DebtorStage
from imagetocash.workflow.stage3_products import ProductsStage
from imagetocash.workflow.stage4_save_order import SaveOrderStage
from imagetocash.workflow.stage5_invoice import InvoiceStage


class Stage(Protocol):
    def run(self, ctx: RunContext) -> None: ...


class ExitCode(IntEnum):
    DONE = 0
    ERROR = 1
    MANUAL_REVIEW = 2


@dataclass(frozen=True)
class RunOutcome:
    exit_code: ExitCode
    report: Path
    message: str


def required_fields_missing(order: OrderDocument) -> list[str]:
    """Spec 1.2: the fields the rest of the flow cannot do without."""
    debtor = order.debtor
    checks = {
        "External Reference": order.external_reference,
        "Company or customer name": debtor.search_text,
        "billing street / ZIP / City": debtor.billing_address.street
        and debtor.billing_address.zip_code
        and debtor.billing_address.city,
        "Payment Method": order.payment.method,
        "Paid Status": order.payment.paid_status,
    }
    missing = [name for name, value in checks.items() if not value]
    missing += [f"item {i.position} SKU" for i in order.items if not i.sku]
    return missing


class ImageToCashRunner:
    def __init__(
        self,
        extractor: OrderExtractor,
        connect_ui: Callable[[], FakturamaUi],
        evidence: EvidenceRecorder,
        start_app_early: Callable[[], None] = lambda: None,
    ) -> None:
        self._extractor = extractor
        self._connect_ui = connect_ui
        self._evidence = evidence
        self._start_app_early = start_app_early

    def run(self, image_path: Path) -> RunOutcome:
        try:
            self._start_app_early()  # JVM boots while the LLM reads the image (the only parallel part)
            order = self._extract_and_validate(image_path)
            ui = self._connect_ui()
            ctx = RunContext(order=order, evidence=self._evidence)
            stages: tuple[Stage, ...] = (
                OpenOrderStage(ui),
                DebtorStage(ui),
                ProductsStage(ui),
                SaveOrderStage(ui),
                InvoiceStage(ui),
            )
            for number, stage in enumerate(stages, start=1):
                stage.run(ctx)
                self._evidence.stage_done(str(number))
        except ManualReviewRequired as stop:
            report = self._evidence.write_report(f"MANUAL REVIEW at {stop.spec_step}")
            return RunOutcome(ExitCode.MANUAL_REVIEW, report, str(stop))
        except Exception as error:
            report = self._evidence.write_report(f"ERROR: {type(error).__name__}")
            return RunOutcome(ExitCode.ERROR, report, f"{type(error).__name__}: {error}")
        report = self._evidence.write_report("DONE: Order and linked Invoice saved and verified")
        return RunOutcome(ExitCode.DONE, report, f"Order {ctx.order_number} and its Invoice verified")

    def _extract_and_validate(self, image_path: Path) -> OrderDocument:
        ev = self._evidence
        with ev.spec_step("1.1", "Extract and normalize the order image", expected=image_path.name) as rec:
            extracted = self._extractor.extract(image_path)
            (ev.run_dir / "extracted.json").write_text(extracted.model_dump_json(indent=2), encoding="utf-8")
            order = to_order_document(extracted)
            ensure_order_is_consistent(order)
            rec.observed = f"{len(order.items)} item(s), total {order.totals.gross} {order.currency}"
        with ev.spec_step("1.2", "All required fields extracted") as rec:
            missing = required_fields_missing(order)
            if missing:
                raise ManualReviewRequired("1.2", ReviewReason.EXTRACTION_INVALID, "missing: " + ", ".join(missing))
            rec.observed = json.dumps(
                {
                    "reference": order.external_reference,
                    "debtor": order.debtor.company,
                    "payment": order.payment.method,
                    "paid": order.payment.paid_status,
                }
            )
        return order
