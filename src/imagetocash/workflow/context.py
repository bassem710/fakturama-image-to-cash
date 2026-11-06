"""The state one run carries from stage to stage."""

from __future__ import annotations

from dataclasses import dataclass, field

from imagetocash.domain.models import OrderDocument
from imagetocash.workflow.protocols import Evidence, Row


@dataclass
class RunContext:
    """State carried through stages 1-5 of one run."""

    order: OrderDocument
    evidence: Evidence
    order_number: str = ""
    invoice_number: str = ""
    debtor_row: Row | None = None
    product_rows: dict[str, Row] = field(default_factory=dict)  # sku -> selected row
