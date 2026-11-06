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

    Which separator is the decimal one:
    - both '.' and ',' present: the LAST one ('1.234,567' -> 1234.567);
    - one separator kind, used more than once: thousands ('1.234.567');
    - one separator, once: decimal, unless exactly 3 digits follow AND a non-zero group of 1-3
      digits precedes it, which is the thousands form ('1.234' -> 1234, but '0,125' -> 0.125).
    """
    cleaned = _NUMBER_CHARS.sub("", fix_ocr_percent(text or ""))
    if not cleaned or cleaned in {"-", ".", ","}:
        raise ParseError(f"no number in {text!r}")
    normalized = _with_decimal_point(cleaned)
    try:
        return Decimal(normalized)
    except InvalidOperation as error:
        raise ParseError(f"cannot read {text!r} as a number") from error


def _with_decimal_point(cleaned: str) -> str:
    """`cleaned` holds only digits, '-', '.' and ','; returns it with '.' as the only separator."""
    last_sep = max(cleaned.rfind("."), cleaned.rfind(","))
    if last_sep == -1:
        return cleaned
    integer_part, fraction = cleaned[:last_sep], cleaned[last_sep + 1 :]
    separator = cleaned[last_sep]
    other = "," if separator == "." else "."
    is_decimal = other in cleaned or (
        separator not in integer_part
        and not (len(fraction) == 3 and 1 <= len(integer_part.lstrip("-")) <= 3 and integer_part.strip("-0"))
    )
    if not is_decimal:
        return cleaned.replace(".", "").replace(",", "")
    return f"{integer_part.replace('.', '').replace(',', '')}.{fraction}"


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
