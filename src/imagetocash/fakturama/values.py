"""How Fakturama writes values, in one place: amounts and percentages in fields ('$250.00', '19.00 %'),
dates in fields ('Jul 14, 2026') and in list copies ('Tue Jul 14 00:00:00 EET 2026' or ISO), and the
raw model values a NatTable copy returns (fractions: VAT 19% -> '0.19', a 10% line discount -> '-0.1')."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from imagetocash.domain.pricing import round_money
from imagetocash.extraction.parsing import ParseError, parse_amount

_JAVA_DATE = re.compile(r"[A-Za-z]{3} (?P<md>[A-Za-z]{3} \d{1,2}) \d{2}:\d{2}:\d{2} \S+ (?P<y>\d{4})")
_TAX_VALUE = re.compile(r"\btaxValue: \[([^\]]*)\]")  # the Items grid copies a whole VAT record
_ISO_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def number_text(text: str) -> str:
    """Canonical number text for comparisons: '$250.00' -> '250', '0.00 %' -> '0', '2.50' -> '2.5'.
    Unreadable text is returned stripped, so it never equals a number by accident."""
    try:
        return format(parse_amount(text).normalize(), "f")
    except (ParseError, InvalidOperation):
        return text.strip()


def same_number(a: str, b: str) -> bool:
    return number_text(a) == number_text(b)


def is_zero(text: str) -> bool:
    return number_text(text) == "0"


def money_text(text: str) -> str:
    """'$1,234.5' -> '1234.50' (two decimals); unreadable text is returned stripped."""
    try:
        return str(round_money(parse_amount(text)))
    except (ParseError, InvalidOperation):
        return text.strip()


def iso_date(text: str, ui_format: str) -> str:
    """A date shown in a field (`ui_format`, e.g. '%b %d, %Y') or copied from a list (ISO date/time or
    Java's Date text, whose zone name '%Z' cannot parse) -> 'YYYY-MM-DD'. Unreadable text is returned
    as it is, so a comparison with an ISO date fails visibly."""
    value = text.strip()
    if java := _JAVA_DATE.fullmatch(value):
        return datetime.strptime(f"{java['md']} {java['y']}", "%b %d %Y").date().isoformat()
    for fmt in (ui_format, *_ISO_FORMATS):
        candidate = value if "%H" in fmt or fmt == ui_format else value[:10]
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def fraction_to_percent(raw: str) -> str:
    """A copied model fraction -> percent text: '0.19' -> '19%'. Also reads the VAT record the Items
    grid copies ('VAT taxValue: [0.19] ...') and a line discount, which Fakturama stores NEGATIVE
    ('-0.1' = 10%), as its size."""
    if found := _TAX_VALUE.search(raw):
        raw = found.group(1)
    try:
        return f"{(abs(Decimal(raw)) * 100).normalize():f}%"
    except InvalidOperation:
        return raw
