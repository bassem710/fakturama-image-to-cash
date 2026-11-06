from __future__ import annotations

from dataclasses import dataclass, field

from imagetocash.automation.evidence import EvidenceRecorder
from imagetocash.domain.models import OrderDocument
from imagetocash.workflow.protocols import Row


@dataclass
class RunContext:
    """State carried through stages 1-5 of one run."""

    order: OrderDocument
    evidence: EvidenceRecorder
    order_number: str = ""
    invoice_number: str = ""
    debtor_row: Row | None = None
    product_rows: dict[str, Row] = field(default_factory=dict)  # sku -> selected row
