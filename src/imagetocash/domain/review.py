"""Manual review: the flow's deliberate, safe stop ("when in doubt, skip")."""

from enum import StrEnum


class ReviewReason(StrEnum):
    EXTRACTION_INVALID = "extraction_invalid"
    TOTALS_MISMATCH = "totals_mismatch"
    AMBIGUOUS_MATCH = "ambiguous_match"
    CONFLICTING_MATCH = "conflicting_match"
    ALREADY_BOOKED_PARTIAL = "already_booked_partial"  # this order is in Fakturama, but incomplete
    CREATED_RECORD_NOT_FOUND = "created_record_not_found"
    VALUE_MISMATCH = "value_mismatch"
    UNSUPPORTED_PAYMENT_METHOD = "unsupported_payment_method"
    PAYMENT_METHOD_UNAVAILABLE = "payment_method_unavailable"
    UI_ELEMENT_NOT_FOUND = "ui_element_not_found"
    NOT_IMPLEMENTED = "not_implemented"


class ManualReviewRequired(Exception):
    """Raised when the automation must stop and hand the case to a person.

    `spec_step` is the step number from the take-home PDF (e.g. "2.3") so the
    stop can be traced straight back to the instruction that caused it.
    """

    def __init__(self, spec_step: str, reason: ReviewReason, detail: str) -> None:
        super().__init__(f"[{spec_step}] {reason}: {detail}")
        self.spec_step = spec_step
        self.reason = reason
        self.detail = detail
