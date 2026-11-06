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

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation

Record = Mapping[str, str]
Normalizer = Callable[[str], str]


def normalize_text(value: str | None) -> str:
    """Case-insensitive, whitespace-collapsed comparison form."""
    return " ".join((value or "").split()).casefold()


_OCR_CONFUSABLES = str.maketrans({"o": "0", "i": "1", "l": "1", "|": "1", "s": "5", "b": "8"})


def normalize_ocr_text(value: str | None) -> str:
    """Comparison form for text READ BY OCR: folds characters OCR commonly confuses
    (O/0, I/l/1, S/5, B/8) on BOTH sides, so 'CHR-ERG-OI' (OCR) equals 'CHR-ERG-01' (source).
    Both values are folded identically, so equality stays symmetric; the price is that two
    codes differing only in a confusable pair also compare equal, which is documented."""
    return normalize_text(value).translate(_OCR_CONFUSABLES)


_OCR_PERCENT_GLYPH = re.compile(r"\s*[0oO°]\s*/\s*[0oO°]\s*$")
_ELLIPSIS = ("...", "…")


def fix_ocr_percent(text: str) -> str:
    """Windows OCR reads the UI's '%' as '0/0' ('0.00 %' -> '0.00 0/0'); restore it."""
    return _OCR_PERCENT_GLYPH.sub("%", text)


def normalize_percent(value: str | None) -> str:
    """'19', '19%', '19.00 %', '19,0', OCR '19.00 0/0' -> '19'."""
    text = normalize_text(fix_ocr_percent(value or "")).replace("%", "").replace(",", ".").strip()
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
    default_normalizer: Normalizer = normalize_text
    # Fields whose list cell may be truncated ('Northstar Offi...') and still count as exact. Only a
    # field the list was already FILTERED on belongs here: the filter guarantees the full value is in
    # the row, so the prefix cannot belong to another record. A truncated cell in any other field
    # makes the row a near-miss (stop), never an exact match.
    truncatable_fields: tuple[str, ...] = ()

    def ocr_tolerant(self) -> RecordMatchPolicy:
        """Same rules, for rows that were read by OCR."""
        return replace(self, default_normalizer=normalize_ocr_text)

    def _normalized(self, record: Record, field_name: str) -> str:
        normalize = self.normalizers.get(field_name, self.default_normalizer)
        return normalize(record.get(field_name, ""))

    def _compare(self, wanted: Record, row: Record, field_name: str) -> str:
        """'same', 'prefix' (a truncated cell whose visible part matches) or 'differs'."""
        expected, shown = self._normalized(wanted, field_name), self._normalized(row, field_name)
        if shown.endswith(_ELLIPSIS):  # a narrow list column truncated the value: compare the prefix
            prefix = shown.rstrip(".…").strip()
            return "prefix" if len(prefix) >= 3 and expected.startswith(prefix) else "differs"
        return "same" if expected == shown else "differs"

    def _exact(self, wanted: Record, row: Record, field_names: Sequence[str]) -> bool:
        for name in field_names:
            result = self._compare(wanted, row, name)
            if result == "differs" or (result == "prefix" and name not in self.truncatable_fields):
                return False
        return True

    def _related(self, wanted: Record, row: Record, field_names: Sequence[str]) -> bool:
        return all(self._compare(wanted, row, f) != "differs" for f in field_names)

    def evaluate(self, wanted: Record, rows: Sequence[Record]) -> MatchOutcome:
        all_fields = (*self.identity_fields, *self.checked_fields)
        exact_rows = tuple(r for r in rows if self._exact(wanted, r, all_fields))
        if len(exact_rows) == 1:
            return ExactMatch(exact_rows[0])
        if len(exact_rows) > 1:
            return AmbiguousMatch(exact_rows)
        conflicting_rows = tuple(r for r in rows if self._related(wanted, r, self.identity_fields))
        if conflicting_rows:
            return ConflictingMatch(conflicting_rows)
        # Duplicate guard: a row that mentions the identity anywhere (e.g. a misread column) is a
        # reason to stop, never to create a second record.
        mentioning = tuple(r for r in rows if self._mentions_identity(wanted, r))
        if mentioning:
            return ConflictingMatch(mentioning)
        return NoMatch()

    def _mentions_identity(self, wanted: Record, row: Record) -> bool:
        """Every NON-EMPTY identity value appears somewhere in the row (a private customer has no
        company; its names still count)."""
        joined = normalize_ocr_text(" ".join(row.values()))
        identity = [v for f in self.identity_fields if (v := normalize_ocr_text(wanted.get(f, "")))]
        return bool(identity) and all(value in joined for value in identity)


# Spec 2.3: Company, First Name, Name, ZIP and City must all match.
# The address selector is searched by the company (Debtor.search_text), so only that cell may be truncated.
DEBTOR_MATCH_POLICY = RecordMatchPolicy(
    identity_fields=("company", "first_name", "last_name"),
    checked_fields=("zip", "city"),
    truncatable_fields=("company",),
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
