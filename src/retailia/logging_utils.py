"""Logging that never writes customer content.

The assistant logs only event names, tool names, durations and counts. As a
backstop, :class:`PiiRedactingFilter` masks emails, long digit runs (phone,
card or tracking numbers) and street addresses in any record that slips through.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b\d{3}[ -]?\d{4}\b|\b\d{8,}\b"), "[number]"),
    (re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+\s+(?:Street|Avenue|Road|Lane|Boulevard|St|Ave|Rd)\b"), "[address]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class PiiRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def get_logger(name: str = "retailia") -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, PiiRedactingFilter) for f in logger.filters):
        logger.addFilter(PiiRedactingFilter())
    return logger
