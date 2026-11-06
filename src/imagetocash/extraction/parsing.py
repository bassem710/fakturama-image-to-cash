"""Deterministic text -> Decimal / date conversion for printed values."""

import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from imagetocash.domain.matching import fix_ocr_percent

DEFAULT_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d")

_NUMBER_CHARS = re.compile(r"[^0-9,.\-]")


class ParseError(ValueError):
    pass


def parse_amount(text: str) -> Decimal:
    """'EUR 1.234,56' -> 1234.56, '570.00' -> 570.00, '10%' -> 10, '-3,5' -> -3.5.

    The decimal separator is the LAST '.' or ',' when it is followed by 1-2 digits;
    any other separator is a thousands separator.
    """
    cleaned = _NUMBER_CHARS.sub("", fix_ocr_percent(text or ""))
    if not cleaned or cleaned in {"-", ".", ","}:
        raise ParseError(f"no number in {text!r}")
    last_sep = max(cleaned.rfind("."), cleaned.rfind(","))
    if last_sep != -1 and 1 <= len(cleaned) - last_sep - 1 <= 2:
        integer_part = cleaned[:last_sep].replace(".", "").replace(",", "")
        normalized = f"{integer_part}.{cleaned[last_sep + 1 :]}"
    else:
        normalized = cleaned.replace(".", "").replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation as error:
        raise ParseError(f"cannot read {text!r} as a number") from error


def parse_percent(text: str | None, default: Decimal = Decimal(0)) -> Decimal:
    if text is None or not text.strip():
        return default
    return parse_amount(text)


def parse_date(text: str, formats: Sequence[str] = DEFAULT_DATE_FORMATS) -> date:
    value = (text or "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"cannot read {text!r} as a date (tried {', '.join(formats)})")


def split_contact_name(full_name: str) -> tuple[str, str]:
    """'Marta Klein' -> ('Marta', 'Klein'); multi-part first names keep all but the last word."""
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]
