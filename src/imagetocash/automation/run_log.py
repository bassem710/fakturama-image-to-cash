"""Step logging without sensitive data.

Order data is treated like patient data: logs show spec step, action, result, reason code and
duration. Values are MASKED (first and last character plus length), and every free-text message
passes `redact()` first, so names, addresses, emails, phone numbers, references and amounts never
reach the console, run.log, steps.jsonl or report.md in clear text.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

LOGGER_NAME = "imagetocash"

# One quote style at a time, shortest match, empty values included: "'' lacks ... name='X'" must
# mask '' and 'X' separately (seen live: a greedy pairing left the real value in clear text).
_QUOTED = re.compile(r"'(?P<v1>[^'\n]{0,300}?)'|\"(?P<v2>[^\"\n]{0,300}?)\"")
# name=value without quotes: the value runs to the next , ; ) | or line end, so EVERY word of a
# multi-word value is masked ("city=Frankfurt am Main"), not only the first.
_BARE_FIELD = re.compile(r"\b(?P<k>[a-z_]{2,30})=(?!<masked>|')[^,;)|\n]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s/().-]{6,}\d")
_NUMBER = re.compile(r"(?<![A-Za-z])\d[\d.,]*")


def mask(value: object) -> str:
    """'Northstar Office GmbH' -> 'N***H (21 chars)'. Short values reveal nothing."""
    text = str(value or "")
    if not text:
        return "<empty>"
    if len(text) <= 3:
        return f"*** ({len(text)} chars)"
    return f"{text[0]}***{text[-1]} ({len(text)} chars)"


def redact(text: object) -> str:
    """Mask quoted values, emails, phone numbers and numbers inside a free-text message."""
    out = str(text or "")
    out = _QUOTED.sub(lambda m: f"'{mask(m.group('v1') if m.group('v1') is not None else m.group('v2'))}'", out)
    out = _BARE_FIELD.sub(lambda m: f"{m.group('k')}=<masked>", out)
    out = _EMAIL.sub("<email>", out)
    out = _PHONE.sub("<phone>", out)
    return _NUMBER.sub("#", out)


class _JsonLines(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False)


def setup_run_logging(run_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    logger.addHandler(console)
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
        file_handler.setFormatter(_JsonLines())
        logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
