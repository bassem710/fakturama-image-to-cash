"""Spec 2.10.4: map the extracted Payment Method to Fakturama's payment-code dropdown."""

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.review import ManualReviewRequired, ReviewReason

PAYMENT_CODE_BY_METHOD: dict[str, str] = {
    "bank transfer": "Credit transfer",
    "credit card": "Credit card",
    "sepa direct debit": "SEPA direct debit",
}


def payment_code_for(payment_method: str) -> str:
    code = PAYMENT_CODE_BY_METHOD.get(normalize_text(payment_method))
    if code is None:
        raise ManualReviewRequired(
            "2.10.4",
            ReviewReason.UNSUPPORTED_PAYMENT_METHOD,
            f"No payment-code mapping for {payment_method!r}",
        )
    return code
