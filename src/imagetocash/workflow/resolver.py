"""The one decision rule shared by Debtor (2.3), Payment Method (2.10.2), Product (3.3) and VAT (3.5):

exactly one exact row  -> use it
several exact rows     -> stop (ambiguous)
only near-misses       -> stop (conflicting)
nothing related        -> caller creates the record, then require_exact() confirms it
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from imagetocash.domain.matching import (
    AmbiguousMatch,
    ConflictingMatch,
    ExactMatch,
    NoMatch,
    RecordMatchPolicy,
)
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.protocols import Row


def _describe(rows: Sequence[Row]) -> str:
    return "; ".join(", ".join(f"{k}={v}" for k, v in row.items()) for row in rows[:5])


def decide(policy: RecordMatchPolicy, wanted: Mapping[str, str], rows: Sequence[Row], spec_step: str) -> Row | None:
    """Return the single exact row, None when the record must be created, or stop for review."""
    match policy.evaluate(wanted, rows):
        case ExactMatch(row):
            return row
        case AmbiguousMatch(found):
            raise ManualReviewRequired(spec_step, ReviewReason.AMBIGUOUS_MATCH, _describe(found))
        case ConflictingMatch(found):
            raise ManualReviewRequired(spec_step, ReviewReason.CONFLICTING_MATCH, _describe(found))
        case NoMatch():
            return None
    raise AssertionError("unreachable")


def require_exact(policy: RecordMatchPolicy, wanted: Mapping[str, str], rows: Sequence[Row], spec_step: str) -> Row:
    """After creating a record it must be selectable exactly once (2.12, 3.12, 2.10.6, 3.6)."""
    row = decide(policy, wanted, rows, spec_step)
    if row is None:
        raise ManualReviewRequired(
            spec_step, ReviewReason.CREATED_RECORD_NOT_FOUND, f"not found after creation: {dict(wanted)}"
        )
    return row
