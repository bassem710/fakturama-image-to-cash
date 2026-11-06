"""Duplicate guard (added to the spec, step 1.2.1): before 1.3 creates anything, look the External
Reference up in Data > Documents. Read-only: it opens a list, never an editor."""

from __future__ import annotations

from imagetocash.workflow.checks import ExistingBooking, classify_existing
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi

STEP = "1.2.1"


class AlreadyBookedGuard:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui

    def run(self, ctx: RunContext) -> ExistingBooking | None:
        """None -> book the order. ExistingBooking -> it is already booked and verified; stop
        without changes. Raises ManualReviewRequired for partial or conflicting earlier work."""
        reference = ctx.order.external_reference
        with ctx.evidence.spec_step(STEP, "Already booked? Data > Documents by Cust.Ref.", expected=reference) as rec:
            self._ui.documents.open()
            rows = self._ui.documents.rows_for_reference(reference)
            existing = classify_existing(rows, ctx.order, STEP)
            rec.observed = "not booked yet" if existing is None else "already booked and verified"
        return existing
