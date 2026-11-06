"""Exact-match rules for master data (spec 2.3, 2.10.2, 3.3, 3.5).

Rows are plain `Mapping[str, str]` records, which is what a screen reads from
a list (by UIA or OCR). Each policy names:

- identity fields: what makes two records "the same thing" (Company + names, SKU, VAT name)
- checked fields:  fields that must also match for an *exact* match (ZIP, City, VAT value...)

Outcomes:
- ExactMatch        exactly one row matches every field
- AmbiguousMatch    two or more rows match every field
- ConflictingMatch  no exact row, but a row shares the identity and differs in a checked field
- NoMatch           nothing related exists -> the caller may create the record
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

Record = Mapping[str, str]
Normalizer = Callable[[str], str]


def normalize_text(value: str | None) -> str:
    """Case-insensitive, whitespace-collapsed comparison form."""
    return " ".join((value or "").split()).casefold()


def normalize_percent(value: str | None) -> str:
    """'19', '19%', '19.00 %', '19,0' -> '19'."""
    text = normalize_text(value).replace("%", "").replace(",", ".").strip()
    try:
        return format(Decimal(text).normalize(), "f")
    except InvalidOperation:
        return text


def normalize_code(value: str | None) -> str:
    """'S (Standard rate)' -> 's' (first token is the code)."""
    tokens = normalize_text(value).split()
    return tokens[0] if tokens else ""


@dataclass(frozen=True)
class ExactMatch:
    row: Record


@dataclass(frozen=True)
class AmbiguousMatch:
    rows: tuple[Record, ...]


@dataclass(frozen=True)
class ConflictingMatch:
    rows: tuple[Record, ...]


@dataclass(frozen=True)
class NoMatch:
    pass


MatchOutcome = ExactMatch | AmbiguousMatch | ConflictingMatch | NoMatch


@dataclass(frozen=True)
class RecordMatchPolicy:
    identity_fields: tuple[str, ...]
    checked_fields: tuple[str, ...] = ()
    normalizers: Mapping[str, Normalizer] = field(default_factory=dict)

    def _normalized(self, record: Record, field_name: str) -> str:
        normalize = self.normalizers.get(field_name, normalize_text)
        return normalize(record.get(field_name, ""))

    def _fields_equal(self, wanted: Record, row: Record, field_names: Sequence[str]) -> bool:
        return all(self._normalized(wanted, f) == self._normalized(row, f) for f in field_names)

    def evaluate(self, wanted: Record, rows: Sequence[Record]) -> MatchOutcome:
        all_fields = (*self.identity_fields, *self.checked_fields)
        exact_rows = tuple(r for r in rows if self._fields_equal(wanted, r, all_fields))
        if len(exact_rows) == 1:
            return ExactMatch(exact_rows[0])
        if len(exact_rows) > 1:
            return AmbiguousMatch(exact_rows)
        conflicting_rows = tuple(r for r in rows if self._fields_equal(wanted, r, self.identity_fields))
        if conflicting_rows:
            return ConflictingMatch(conflicting_rows)
        return NoMatch()


# Spec 2.3: Company, First Name, Name, ZIP and City must all match.
DEBTOR_MATCH_POLICY = RecordMatchPolicy(
    identity_fields=("company", "first_name", "last_name"),
    checked_fields=("zip", "city"),
)

# Spec 3.3: exact SKU (Fakturama's "Item Number").
PRODUCT_MATCH_POLICY = RecordMatchPolicy(identity_fields=("sku",))

# Spec 3.5: Name "VAT n%", Value n and VAT code (E-Invoice) S.
VAT_MATCH_POLICY = RecordMatchPolicy(
    identity_fields=("name",),
    checked_fields=("value", "code"),
    normalizers={"value": normalize_percent, "code": normalize_code},
)

# Spec 2.10.2: exact Payment Method name; a different payment code is a conflicting definition.
PAYMENT_METHOD_MATCH_POLICY = RecordMatchPolicy(identity_fields=("name",))


def vat_name_for(vat_percent: Decimal) -> str:
    """Spec 3.4/3.6: 'VAT' followed by the percentage, e.g. 'VAT 19%' or 'VAT 7.5%'."""
    return f"VAT {normalize_percent(str(vat_percent))}%"
